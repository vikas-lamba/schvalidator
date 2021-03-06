#
# Copyright (c) 2016 SUSE Linux GmbH
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 3 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, contact SUSE LLC.
#
# To contact SUSE about this file by physical or electronic mail,
# you may find current contact information at www.suse.com

from .common import NSMAP, OLD_SCHEMA_TAG, ROLEDICT, SCHEMA_TAG
from .exceptions import (OldSchematronError,
                         NoISOSchematronFileError,
                         )

import logging
from lxml import etree
from lxml.isoschematron import Schematron

log = logging.getLogger(__package__)


class NSElement(object):
    def __init__(self, namespace, prefix=None):
        self.ns = namespace
        self.prefix = prefix

    def __call__(self, name):
        return etree.QName(self.ns, name)

    def __getattr__(self, name):
        return self(name)

    def __repr__(self):
        if self.prefix is None:
            result = "%s(%s)" % (self.__class__.__name__, self.ns)
        else:
            result = "%s(%s=%s)" % (self.__class__.__name__,
                                    self.prefix,
                                    self.ns
                                    )
        return result


svrl = NSElement(NSMAP['svrl'])


def role2level(rolelevel):
    """Return the log level
    :param str rolelevel: The value of the ``role`` attribute
    :return: int
    """
    return ROLEDICT.get(rolelevel)


def check4schematron(schema, xmlparser=None):
    """Check if file is a ISO Schematron schema

    :param str schema: Filename of the Schematron schema
    :param xmlparser: :class:`etree.XMLParser` object
    :raises: OldSchematronError or NoISOSchematronFileError
    """
    schtree = etree.parse(schema, parser=xmlparser)
    roottag = schtree.getroot().tag
    log.debug("Found root element: %r", roottag)

    if roottag == OLD_SCHEMA_TAG:
        raise OldSchematronError("File %r is an old Schematron schema."
                                 "This program supports only ISO Schematron" %
                                 schema)
    elif roottag != SCHEMA_TAG:
        raise NoISOSchematronFileError('File %r not an ISO Schematron' %
                                       schema)
    # After this point, everything is ok now
    return schtree


def validate_sch(schema, xmlfile, phase=None, xmlparser=None):
    """Validate XML with Schematron schema

    :param str schema: Filename of the Schematron schema
    :param str xmlfile: Filename of the XML file
    :param str phase: Phase of the Schematron schema
    :param xmlparser: :class:`etree.XMLParser` object
    :return: The result of the validation and the
             Schematron result tree as class :class:`etree._XSLTResultTree`
    :rtype: tuple
    """
    log.debug("Try to validate XML=%r with SCH=%r", xmlfile, schema)
    if xmlparser is None:
        # Use our default XML parser:
        xmlparser = etree.XMLParser(encoding="UTF-8",
                                    no_network=True,
                                    )
    doctree = etree.parse(xmlfile, parser=xmlparser)
    schema = check4schematron(schema, xmlparser)

    log.debug("Schematron validation with file=%r, schema=%r, phase=%r",
              xmlfile, schema, phase)
    schematron = Schematron(schema,
                            phase=phase,
                            store_report=True,
                            store_xslt=True)
    result = schematron.validate(doctree)
    log.info("=> Validation result was: %s", result)
    return result, schematron


def extractrole(fa):
    """Try to extract ``role`` attributes either in the ``svrl:failed-assert''
       or in the preceding sibling ``svrl:fired-rule`` element.

    :param fa: the current `svrl:failed-assert`` element
    :return: attribute value of ``role``, otherwise None if not found
    :rtype: str | None
    """
    try:
        role = list(fa.itersiblings(svrl('fired-rule').text,
                                    preceding=True)
                    )[0].attrib.get('role')
    except IndexError:
        role = None

    # Overwrite with next role, if needed
    role = role if fa.attrib.get('role') is None else fa.attrib.get('role')
    return role


def process_result_svrl(report):
    """Process the report tree

    :param report: tree of :class:`lxml.etree._XSLTResultTree`
    """

    for idx, fa in enumerate(report.iter(svrl("failed-assert").text), 1):
        text = fa[0].text.strip()
        loc = fa.attrib.get('location')

        # The ``role`` attribute contains contains the log level
        level = role2level(extractrole(fa))

        log.log(level,
                "No. %i\n"
                "\tLocation: %r\n"
                "\tMessage:%s\n"
                "%s",
                idx, loc, text, "-" * 20)


def save_reportfile(schematron, args):
    """Save the report file from the --report option

    :param schematron: the Schematron object
    :type schematron: :class:`lxml.isoschematron.Schematron`
    :param dict args: Dictionary of parsed CLI arguments
    """
    reportfile = args['--report']

    if reportfile is not None:
        schematron.validation_report.write(reportfile,
                                           pretty_print=True,
                                           encoding="utf-8",
                                           )
        log.info("Wrote Schematron validation report to %r", reportfile)
    else:
        log.debug(schematron.validation_report)


def save_xsltfile(schematron, args):
    """Save the validation XSLT tree from the --store-xslt option

    :param schematron: the Schematron object
    :type schematron: :class:`lxml.isoschematron.Schematron`
    :param dict args: Dictionary of parsed CLI arguments
    """
    xsltfile = args['--store-xslt']
    if xsltfile is not None:
        schematron.validator_xslt.write(xsltfile,
                                        pretty_print=True,
                                        encoding="utf-8",
                                        )
        log.info("Wrote validation XSLT file to %r", xsltfile)


def process(args):
    """Process the validation and the result

    :param dict args: Dictionary of parsed CLI arguments
    :return: return exit value
    :rtype: int
    """
    result, schematron = validate_sch(args['SCHEMA'],
                                      args['XMLFILE'],
                                      phase=args['--phase'],
                                      )
    save_reportfile(schematron, args)
    save_xsltfile(schematron, args)
    process_result_svrl(schematron.validation_report)

    if not result:
        log.fatal("Validation failed!")
        return 200
    else:
        log.info("Validation was successful")
    return 0
