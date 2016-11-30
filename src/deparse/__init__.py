#!/usr/bin/env python3
# encoding=utf8 ---------------------------------------------------------------
# Project           : FF-Deps
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-11-25
# Last modification : 2016-11-30
# -----------------------------------------------------------------------------

import os, re, glob, argparse, fnmatch

VERSION = "0.0.0"
LICENSE = "http://ffctn.com/doc/licenses/bsd"

__doc__ = """
Extracts/lists dependencies from Paml and Sugar files. Dependencie are
list of couples `(<type>, <name>)` where type is a string like
`<language>:<type>`, for instance `js:file`, `js:module`, etc.

The modules features both an API and a command-line interface.
"""

class LineParser(object):
	"""An abstract line-based parser. It looks for lines matching the
	regular expressions defined the `LINES` map and executes the corresponding
	method of the subclass with `(line, match)` as arguments."""

	LINES = {}

	def __init__( self ):
		self.path     = None
		self.provides = []
		self.requires = []

	def parsePath( self, path ):
		self.path = path
		with open(path) as f:
			for line in f.readlines():
				self.parseLine(line)
		self.path = None
		return self

	def parse( self, text ):
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

	def onJavaScriptRequire( self, line, match, type="js"):
		reqs = line.split("(",1)[1].rsplit(")",1)[0].split(",")
		for name in reqs:
			self.requires.append(("js:module", name))

	def onJavaScriptGModule( self, line, match ):
		return self.onJavaScriptRequire(line, match, type="js:gmodule")

	def onInclude( self, line, match ):
		line = line[len(match.group()):]
		line = line.split("+",1)[0].strip
		self.requires.append(("paml:file", line))

# -----------------------------------------------------------------------------
#
# SUGAR PARSER
#
# -----------------------------------------------------------------------------

class Sugar(LineParser):
	"""Dependency parser for Sugar files."""

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
# JAVASCRIPT PARSER
#
# -----------------------------------------------------------------------------

class JavaScript(LineParser):
	"""Dependency parser for JavaScript files."""

	LINES = {
	}

	def parsePath( self, path ):
		module = os.path.basename(path).rsplit("-",1)[0]
		self.provides = [("js:module", module)]
		self.requires = []
		return self

# -----------------------------------------------------------------------------
#
# DEPENENCIES
#
# -----------------------------------------------------------------------------

class Dependencies(object):
	"""Extracts and aggregates dependencies."""

	FILE_TYPES = {
		"paml" : Paml,
		"sjs"  : Sugar,
		"js"   : JavaScript
	}

	def __init__( self ):
		self.provides = []
		self.requires = []
		self.paths    = []
		self.resolved = {}
		self.nodes    = {}

	def fromPath( self, path, recursive=False ):
		"""Lists the dependencies at the given path in import priority."""
		self._fromPath(path, recursive=recursive)
		return {
			"provides":self.provides,
			"resolved":self.resolved,
			"requires":self._sortRequires(self.requires)
		}

	def _fromPath( self, path, recursive=False ):
		"""Helper function of the `fromPath` method."""
		if path in self.paths: return self
		self.paths.append(path)
		ext      = path.rsplit(".",1)[1].lower()
		parser   = self.FILE_TYPES[ext]().parsePath(path)
		self.provides.append((path, parser.provides))
		self.requires = self._merge(self.requires, parser.requires)
		# We register the nodes
		for name in parser.provides:
			if name not in self.nodes: self.nodes[name] = []
			self.nodes[name] = self._merge(self.nodes[name], parser.requires)
		if recursive:
			for dependency in parser.requires:
				for dependency_path in self.resolve(dependency, path):
					self._fromPath(dependency_path, recursive=recursive)

	def _merge( self, a, b ):
		for e in b:
			if e not in a:
				a.append(e)
		return a

	def resolve( self, item, path ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		t, name = item
		res     = ()
		if t == "js:module":
			js_modules  = sorted([_ for _ in glob.glob("lib/js/{0}-*.js".format(name))  if ".gmodules" not in _])
			sjs_modules = sorted([_ for _ in glob.glob("lib/sjs/{0}.sjs".format(name)) + glob.glob("lib/sjs/{0}*-*.sjs".format(name))])
			res = sjs_modules if sjs_modules else (js_modules[-1],)
		elif t == "js:gmodule":
			js_modules  = sorted([_ for _ in glob.glob("lib/js/{0}-*.js".format(name))  if ".gmodules" in _])
			sjs_modules = sorted([_ for _ in glob.glob("lib/sjs/{0}*.sjs".format(name)) + glob.glob("lib/sjs/{0}*-*.sjs".format(name))])
			res = sjs_modules if sjs_modules else (js_modules[-1],)
		else:
			raise Exception("Type not supported: {0}".format(t))
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
			for required in self.nodes[module]:
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
	oparser.add_argument("files", metavar="FILE", type=str, nargs='+', help='The files to extract dependencies from')
	oparser.add_argument("-o", "--output",    type=str,  dest="output", default="-")
	oparser.add_argument("-t", "--type",      type=str,  dest="types",  nargs="+", default=("*",))
	oparser.add_argument("-r", "--recursive", dest="recursive",  action="store_true", default=False)
	oparser.add_argument("-p", "--path",      dest="show_path",  action="store_true", default=False)
	# We create the parse and register the options
	args = oparser.parse_args(args=args)
	res  = run(args.files, recursive=args.recursive)
	out  = sys.stdout
	resolved = []
	for item in res["requires"]:
		t, n = item
		for tp in args.types:
			if fnmatch.fnmatch(t, tp):
				if args.show_path:
					for p in set(res["resolved"].get(item) or ()):
						if p not in resolved:
							resolved.append(p)
							out.write(p)
							out.write("\n")
				else:
					if n not in resolved:
						resolved.append(n)
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

