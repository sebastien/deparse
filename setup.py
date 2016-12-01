#!/usr/bin/python
# Encoding: utf-8
# -----------------------------------------------------------------------------
# Project           :   Deparse
# -----------------------------------------------------------------------------
# Author            :   Sebastien Pierre           <sebastien.pierre@gmail.com>
# License           :   Revised BSD License
# -----------------------------------------------------------------------------
# Creation date     :   2016-11-28
# Last mod.         :   2016-11-30
# -----------------------------------------------------------------------------

from distutils.core import setup

NAME        = "deparse"
VERSION     = "0.2.0"
WEBSITE     = "http://github.com/sebastien/deparse/" + NAME.lower()
SUMMARY     = "Multi-language dependency parsing tool & API"
DESCRIPTION = """\
*Deparse* is both a command-line tool and Python module to parse and list
dependencies in a language-independent way."""

# ------------------------------------------------------------------------------
#
# SETUP DECLARATION
#
# ------------------------------------------------------------------------------

setup(
	name         = NAME,
	version      = VERSION,
	author       = "Sebastien Pierre", author_email = "sebastien.pierre@gmail.com",
	description  = SUMMARY, long_description = DESCRIPTION,
	license      = "Revised BSD License",
	keywords     = "program analysis, dependency management, parsing",
	url          =  WEBSITE,
	download_url =  WEBSITE + "/%s-%s.tar.gz" % (NAME.lower(), VERSION),
	package_dir  = { "": "src" },
	scripts      = ["bin/deparse"],
	packages     = [
		"deparse",
	],
	classifiers = [
	  "Development Status :: 4 - Beta",
	  "Environment :: Console",
	  "Intended Audience :: Developers",
	  "License :: OSI Approved :: BSD License",
	  # TODO: Add more here
	  "Natural Language :: English",
	  "Operating System :: POSIX",
	  "Operating System :: Microsoft :: Windows",
	  "Programming Language :: Python",
	]
)

# EOF - vim: tw=80 ts=4 sw=4 noet
