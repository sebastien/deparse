#!/usr/bin/env python3
# encoding=utf8 ---------------------------------------------------------------
# Project           : FF-Deps
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-11-25
# Last modification : 2016-12-08
# -----------------------------------------------------------------------------

from __future__ import print_function

import sys, os, re, glob, argparse, fnmatch

try:
	import reporter
	logging = reporter.bind("deparse", template=reporter.TEMPLATE_COMMAND)
except ImportError as e:
	import logging

__version__ = "0.2.1"
LICENSE     = "http://ffctn.com/doc/licenses/bsd"

__doc__ = """
*deparse* extracts/lists and resolves dependencies from a variety of files.
Dependencies are listed as couples `(<type>, <name>)` where type is a string like
`<language>:<type>`, for instance `js:file`, `js:module`, etc.

The `deparse` module features both an API and a command-line interface.
"""

class LineParser(object):
	"""An abstract line-based parser. It looks for lines matching the
	regular expressions defined the `LINES` map and executes the corresponding
	method of the subclass with `(line, match)` as arguments."""

	LINES   = {}
	OPTIONS = {}

	def __init__( self ):
		self.path     = None
		self.provides = []
		self.requires = []

	def parsePath( self, path ):
		self.path = path
		with open(path) as f:
			self.onParse(path)
			for line in f.readlines():
				self.parseLine(line)
		self.path = None
		return self

	def parse( self, text, path=None ):
		self.onParse(path or self.path)
		for line in text.split("\n"):
			self.parseLine(line)
		return self

	def relpath( self, path ):
		return os.path.relpath(path, os.path.dirname(self.path)) if self.path else path

	def parseLine( self, line ):
		for name, expr in self.LINES.items():
			match = re.match(expr, line)
			if match:
				getattr(self, name)(line, match)
				break
		return self

	def onParse( self, path ):
		pass

	def resolve( self, item, path ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		t, name = item
		res     = []
		dirs    = [os.getcwd(), os.path.dirname(os.path.abspath(path))]
		# TODO: Support resolvers
		if t == "js:module":
			name = name.replace(".", "/")
			js_modules  = sorted([_ for _ in self._glob(dirs, "lib/js/{0}-*.js".format(name,)) if ".gmodules" not in _])
			sjs_modules = sorted([_ for _ in self._glob(dirs, "lib/sjs/{0}.sjs".format(name ),  "lib/sjs/{0}*-*.sjs".format(name))])
			res = sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		elif t == "js:gmodule":
			name = name.replace(".", "/")
			js_modules  = sorted([_ for _ in self._glob(dirs, "lib/js/{0}-*.js".format(name) ) if ".gmodules" in _])
			sjs_modules = sorted([_ for _ in self._glob(dirs, "lib/sjs/{0}*.sjs".format(name), "lib/sjs/{0}*-*.sjs".format(name))])
			res = sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		elif t.endswith(":file"):
			altname = name + "." + t.split(":",1)[0]
			for n in (name, altname):
				for d in dirs:
					p = os.path.join(d, n)
					if os.path.exists(p):
						res.append(p)
		else:
			raise Exception("Type not supported: {0}".format(t))
		if not res:
			logging.error("Unresolved item in {0}: {1} at {2}".format(self.__class__.__name__, item, path))
		return res

	def _glob( self, dirs, *expressions ):
		matches = []
		for d in dirs:
			for e in expressions:
				p = os.path.join(d, e)
				matches += glob.glob(p)
		return sorted(matches)

# -----------------------------------------------------------------------------
#
# C PARSER
#
# -----------------------------------------------------------------------------

class C(LineParser):
	"""Dependency parser for C files."""

	LINES = {
		"onInclude"  : "^\s*#include\s+[<\"]([^\>\"]+)[>\"]",
	}

	def onParse( self, path ):
		module = os.path.basename(path).rsplit("-",1)[0]
		self.provides = [("c:header", module)]

	def onInclude( self, line, match ):
		self.requires.append(("c:header",match.group(1)))

# -----------------------------------------------------------------------------
#
# JAVASCRIPT PARSER
#
# -----------------------------------------------------------------------------

class JavaScript(LineParser):
	"""Dependency parser for JavaScript files."""

	# SEE: https://github.com/google/closure-library/wiki/goog.module:-an-ES6-module-like-alternative-to-goog.provide
	LINES = {
		"onRequire" : "(var\s+|exports\.)([\w\d_]+)\s*=\s*require\s*\(([^\)]+)\)(\.([\w\d_]+))?(\.([\w\d_]+))?\s*;?",
		"onImport"  : "\s*import\s+({[^}]*}|\*(\s+as\s+[_\-\w]+)|[_\-\w]+)\s*(from\s+['\"]([^'\"]+)['\"])?",
		"onGoogleProvide" : "goog\.(provide|module)\s*\(['\"](^['\"]+)['\"]\)",
		"onGoogleRequire" : "goog\.require\s*\(['\"](^['\"]+)['\"]\)",
	}

	def onParse( self, path ):
		module = os.path.basename(path).rsplit("-",1)[0]
		self.provides = [("js:module", module)]

	def onRequire( self, line, match ):
		decl, name, module, __, symbol, __, subsymbol = match.groups()
		self.requires.append(("js:module", module))

	def onGoogleProvide( self, line, match ):
		self.provides.append(("js:gmodule", match.group(1)))

	def onGoogleRequire( self, line, match ):
		self.requires.append(("js:gmodule", match.group(1)))

	def onImport( self, line, match ):
		module = match.groups()[-1]
		if not module:
			return
		if module.startswith("."):
			path = os.path.normpath(os.path.join(os.path.dirname(self.path or "."), module))
			self.requires.append(("js:file", path))
		else:
			self.requires.append(("js:module", module))

# -----------------------------------------------------------------------------
#
# SUGAR PARSER
#
# -----------------------------------------------------------------------------

class Sugar(LineParser):
	"""Dependency parser for Sugar files."""

	OPTIONS = {
	}

	LINES = {
		"onModule"  : "^@module\s+([^\s]+)",
		"onImport"  : "^@import",
	}

	def __init__( self ):
		super(Sugar, self).__init__()
		self.requires = [("js:module", "extend")]

	def onModule( self, line, match ):
		self.provides.append(("js:module",match.group(1)))

	def onImport( self, line, match ):
		line = line[len(match.group()):]
		if " from " in line: line = line.split(" from ", 1)[1]
		for _ in line.split(","):
			_ = _.strip()
			if _:
				self.requires.append(("js:module",_))

# -----------------------------------------------------------------------------
#
# PAML PARSER
#
# -----------------------------------------------------------------------------

class Paml(LineParser):
	"""Dependency parser for PAML files."""

	LINES = {
		"onJavaScriptTag"     : "^\t+<script\(",
		"onJavaScriptRequire" : "^\t+@require\:js\(",
		"onJavaScriptGModule" : "^\t+@require\:gmodule\(",
		"onInclude"           : "^\t+%include\s*"
	}

	def onJavaScriptTag( self, line, match ):
		src = line.split("src=",1)[1].split(",")[0].split(")")[0]
		if src[0] == src[-1] and src[0] in '"\'': src = src[1:-1]
		self.requires.append(("js:file", src))

	def onJavaScriptRequire( self, line, match, type="js:module"):
		reqs = line.split("(",1)[1].rsplit(")",1)[0].split(",")
		for name in reqs:
			self.requires.append((type, name))

	def onJavaScriptGModule( self, line, match ):
		return self.onJavaScriptRequire(line, match, type="js:gmodule")

	def onInclude( self, line, match ):
		line = line[len(match.group()):]
		line = line.split("+",1)[0].split("{",1)[0].strip()
		type = "paml:file"
		if line.endswith(".svg"):
			type = "*:file"
		self.requires.append((type, line))

# -----------------------------------------------------------------------------
#
# DEPENENCIES
#
# -----------------------------------------------------------------------------

class Dependencies(object):
	"""Extracts and aggregates dependencies."""

	PARSERS = {
		"paml" : Paml,
		"sjs"  : Sugar,
		"js"   : JavaScript,
		"c"    : C,
		"cxx"  : C,
		"c++"  : C,
		"cpp"  : C,
		"h"    : C,
	}

	def __init__( self ):
		self.provides = []
		self.requires = []
		self.paths    = []
		self.resolved = {}
		self.nodes    = {}

	def fromPath( self, path, recursive=False ):
		"""Lists the dependencies at the given path in import priority. This
		method supports paths containing multiple files, for instance:


		```
		lib/js/jquery.js+lodash.js
		```

		will be translated to

		```
		["lib/js/jquery.js", "lib/js/lodash.js"]
		```

		if the file `lib/js/jquery.js+lodash.js` does not exists.
		"""
		self._fromPath(path, recursive=recursive)
		return {
			"provides":self.provides,
			"resolved":self.resolved,
			"requires":self._sortRequires(self.requires)
		}

	def _fromPath( self, path, recursive=False ):
		"""Helper function of the `fromPath` method."""
		if not os.path.exists(path) and "+" in path:
			paths  = path.split("+")
			prefix = os.path.dirname(paths[0])
			paths  = [paths[0]] + [os.path.join(prefix, _) for _ in paths[1:]]
			return [self._fromPath(_, recursive=recursive) for _ in paths]
		elif path in self.paths:
			return self
		elif os.path.isdir(path):
			# We skip directories
			pass
		else:
			self.paths.append(path)
			ext         = path.rsplit(".",1)[-1].lower()
			parser_type = self.PARSERS.get(ext)
			if not parser_type:
				logging.error("Parser not defined for type `{0}` in: {1}".format(ext, path))
				return
			parser      = parser_type().parsePath(path)
			self.provides.append((path, parser.provides))
			self.requires = self._merge(self.requires, parser.requires)
			# We register the nodes
			for name in parser.provides:
				if name not in self.nodes: self.nodes[name] = []
				self.nodes[name] = self._merge(self.nodes[name], parser.requires)
			for dependency in parser.requires:
				resolved = self.resolve(parser, dependency, path)
				if recursive:
					if not resolved:
						logging.error("Cannot recurse on {0} in {1}: dependency {0} cannot be resolved".format(dependency, path))
					for dependency_path in resolved:
						self._fromPath(dependency_path, recursive=recursive)

	def _merge( self, a, b ):
		for e in b:
			if e not in a:
				a.append(e)
		return a

	def resolve( self, parser, item, path ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		res = parser.resolve(item, path) or ()
		t, name = item
		if name not in self.resolved: self.resolved[item] = []
		self.resolved[item] = self._merge(self.resolved[item], res)
		return res

	def _sortRequires( self, requires ):
		"""Sorts the given list of requirements so that the given list is
		returned in loading order."""
		loaded = []
		requires = sorted(requires, key=lambda _:len(self.nodes.get(_) or ()))
		def load(module, loaded=loaded):
			if module in loaded: return
			for required in self.nodes.get(module) or ():
				# NOTE: This is a bug, the modules should not import themselves
				if required == module: continue
				load(required, loaded)
			loaded.append(module)
			return loaded
		for _ in requires:
			load(_)
		return loaded

# -----------------------------------------------------------------------------
#
# COMMAND-LINE INTERFACE
#
# -----------------------------------------------------------------------------

def list( args, recursive=True, resolve=False ):
	"""Lists all the dependencies listed in the given files."""
	deps = Dependencies()
	res  = None
	for _ in args:
		r = (deps.fromPath(_, recursive=recursive))
		if not res:
			res = r
		else:
			res.update(r)
	return res["requires"]

def run( args, recursive=False ):
	"""Extracts the dependencies of the given files."""
	deps = Dependencies()
	res  = None
	for _ in args:
		r = (deps.fromPath(_, recursive=recursive))
		if not res:
			res = r
		else:
			res.update(r)
	return res

def command( args, name=None ):
	"""The command-line interface of this module."""
	USAGE = "{0} FILE...".format(name or os.path.basename(__file__))
	if type(args) not in (type([]), type(())): args = [args]
	oparser = argparse.ArgumentParser(
		prog        = name or os.path.basename(__file__.split(".")[0]),
		description = "Lists dependencies from PAML and Sugar files"
	)
	# TODO: Rework command lines arguments, we want something that follows
	# common usage patterns.
	oparser.add_argument("files", metavar="FILE", type=str, nargs='+', help='The files to extract dependencies from')
	oparser.add_argument("-o", "--output",    type=str,  dest="output", default="-", help="Specifies an output file")
	oparser.add_argument("-t", "--type",      type=str,  dest="types",  nargs="+", default=("*",))
	oparser.add_argument("-r", "--recursive", dest="recursive",  action="store_true", default=False)
	oparser.add_argument("-p", "--path",      dest="show_path",  action="store_true", default=False)
	oparser.add_argument("-a", "--absolute",  dest="abs_path",   action="store_true", default=False)
	# We create the parse and register the options
	args = oparser.parse_args(args=args)
	res  = run(args.files, recursive=args.recursive)
	out  = sys.stdout
	resolved = []
	cwd  = os.getcwd()
	for item in res["requires"]:
		t, n = item
		for tp in args.types:
			if fnmatch.fnmatch(t, tp):
				if args.show_path:
					r = set(res["resolved"].get(item) or ())
					if not r:
						logging.error("Item {0} unresolved".format(item))
					for p in r:
						if p not in resolved:
							resolved.append(p)
							out.write(p if args.abs_path else os.path.relpath(p, cwd))
							out.write("\n")
				else:
					if n not in resolved:
						resolved.append(n)
						out.write(t)
						out.write("\t")
						out.write(n)
						out.write("\n")

# -----------------------------------------------------------------------------
#
# MAIN
#
# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys
	command(sys.argv[1:])

# EOF - vim: ts=4 sw=4 noet

