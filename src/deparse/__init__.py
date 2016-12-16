#!/usr/bin/env python3
# encoding=utf8 ---------------------------------------------------------------
# Project           : FF-Deps
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-11-25
# Last modification : 2016-12-15
# -----------------------------------------------------------------------------

from __future__ import print_function

import sys, os, re, glob, argparse, fnmatch
from   functools import reduce

# TODO: We should introduce a high-level tracker/resolver (maybe as
# catalogue) that does caching. It should basically maintain
# a mapping of the graph:
#
# - (type,name) → path
# - path + provides  → [ (type,name) ]
# - path + requires  → [ (type,name) ]
#
# - find(name|(type,name))
# - depends|requires(path|name|item)
# - provides(path|item)

try:
	import reporter
	logging = reporter.bind("deparse", template=reporter.TEMPLATE_COMMAND)
except ImportError as e:
	import logging

__version__ = "0.3.1"
LICENSE     = "http://ffctn.com/doc/licenses/bsd"

__doc__ = """
*deparse* extracts/lists and resolves dependencies from a variety of files.
Tracker are listed as couples `(<type>, <name>)` where type is a string like
`<language>:<type>`, for instance `js:file`, `js:module`, etc.

The `deparse` module features both an API and a command-line interface.
"""

class LineParser(object):
	"""An abstract line-based parser. It looks for lines matching the
	regular expressions defined the `LINES` map and executes the corresponding
	method of the subclass with `(line, match)` as arguments.

	The `LineParser.PATH` map defines paths where specific item types
	are expected to be found. You can configure these at runtime so that
	the items can be properly resolved by the `resolve` method.
	"""

	LINES   = {}
	OPTIONS = {}
	PATHS   = {
		"js:module"   : ["lib/js"  , ""],
		"js:gmodule"  : ["lib/js"  , ""],
		"sjs:module"  : ["lib/sjs" , ""],
		"sjs:gmodule" : ["lib/sjs" , ""],
		"css:module"  : ["lib/css" , ""],
		"pcss:module" : ["lib/pcss", ""],
	}

	def __init__( self ):
		self.path     = None
		self.provides = []
		self.requires = []

	def parsePath( self, path, type=None ):
		self.path = path
		self.type = type
		with open(path) as f:
			self.onParse(path, type)
			for line in f.readlines():
				self.parseLine(line)
		self.path = None
		self.type = None
		return self

	def parse( self, text, path=None, type=None ):
		self.onParse(path or self.path, type)
		for line in text.split("\n"):
			self.parseLine(line)
		return self

	def normpath( self, path ):
		"""Returns the normalized path, where if the path is relative, it is considered
		relative to the currenlty parsed path, otherwise it will be returned as absolute."""
		if os.path.abspath(path) == path: return path
		return os.path.normpath(os.path.join(os.path.dirname(self.path), path)) if self.path else os.path.normpath(path)

	def parseLine( self, line ):
		for name, expr in self.LINES.items():
			match = re.match(expr, line)
			if match:
				getattr(self, name)(line, match)
				break
		return self

	def onParse( self, path, type ):
		pass

	def resolve( self, item, path, dirs=() ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		t, name = item
		res     = []
		dirs    = [_ for _ in dirs] + [os.getcwd(), os.path.dirname(os.path.abspath(path)) if not os.path.isdir(path) else os.path.abspath(path)]
		# TODO: Support resolvers
		if not t or t == "js:module":
			name = name.replace(".", "/")
			all_dirs = self._subdirs(dirs, *self.PATHS["js:module"])
			js_modules  = sorted([("js:module", _) for _ in self._glob(all_dirs, "{0}-*.js".format(name,)) if ".gmodule" not in _])
			all_dirs = self._subdirs(dirs, *self.PATHS["sjs:module"])
			sjs_modules = sorted([("sjs:module", _) for _ in self._glob(all_dirs, "{0}.sjs".format(name ),  "{0}*-*.sjs".format(name))])
			res += sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		if not t or t == "js:gmodule":
			name = name.replace(".", "/")
			all_dirs = self._subdirs(dirs, *self.PATHS["js:module"])
			js_modules  = sorted([("js:gmodule", _) for _ in self._glob(all_dirs, "{0}-*.js".format(name)) if ".gmodule" in _])
			all_dirs = self._subdirs(dirs, *self.PATHS["sjs:module"])
			sjs_modules = sorted([("sjs:gmodule", _) for _ in self._glob(all_dirs, "{0}*.sjs".format(name), "{0}*-*.sjs".format(name))])
			res += sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		if not t or t == "css:module":
			all_dirs = self._subdirs(dirs, *self.PATHS["css:module"])
			css_modules  = sorted([("css:module",  _) for _ in self._glob(all_dirs, "{0}.css".format(name))])
			all_dirs = self._subdirs(dirs, *self.PATHS["pcss:module"])
			pcss_modules = sorted([("pcss:module", _) for _ in self._glob(all_dirs, "{0}*.pcss".format(name))])
			res += pcss_modules if pcss_modules else (css_modules[-1],) if css_modules else ()
		if not t or t.endswith(":file"):
			altname = name + ("." + t.split(":",1)[0] if t else "")
			for n in (name, altname):
				for d in dirs:
					p = os.path.join(d, n)
					if os.path.exists(p):
						res.append(("*:file", p))
		if t and t.endswith(":url"):
			res.append(item)
		res = self._resolve( res, item, path, dirs=() )
		if not res:
			logging.error("Unresolved item in {0}: {1} at {2}".format(self.__class__.__name__, item, path))
		res = reduce(lambda x,y:x + [y] if y not in x else x, res, [])
		return res

	def _resolve( self, resolved, item, path, dirs ):
		"""Can be overriden to update the result of `resolve`."""
		return resolved

	def _subdirs( self, dirs, *subdirs):
		"""Returns `len(dirs) * len(subdirs)` directories where each `subdir` is joined
		with all the `dirs`."""
		res = []
		for sd in subdirs:
			res += [os.path.join(d,sd) for d in dirs]
		res += dirs
		return res

	def _glob( self, dirs, *expressions ):
		matches = []
		for d in dirs:
			for e in expressions:
				p = os.path.join(d, e)
				matches += glob.glob(p)
		return sorted(matches)

	def export( self ):
		return dict(
			path=self.path,
			provides=self.provides,
			requires=self.requires,
		)

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

	def onParse( self, path, type ):
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

	def onParse( self, path, type ):
		module  = os.path.basename(path).rsplit("-",1)[0]
		self.provides = [(self.type or "js:module", module)]

	def onRequire( self, line, match ):
		decl, name, module, __, symbol, __, subsymbol = match.groups()
		self.requires.append((self.type or "js:module", module))

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
			self.requires.append((self.type or "js:module", module))

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

	def onParse( self, path, type ):
		self.requires = [(self.type or "js:module", "extend")]

	def onModule( self, line, match ):
		self.provides.append((self.type or "js:module",match.group(1)))

	def onImport( self, line, match ):
		line = line[len(match.group()):]
		if " from " in line: line = line.split(" from ", 1)[1]
		for _ in line.split(","):
			_ = _.strip()
			if _:
				self.requires.append((self.type or "js:module",_))

# -----------------------------------------------------------------------------
#
# PAML PARSER
#
# -----------------------------------------------------------------------------

class Paml(LineParser):
	"""Dependency parser for PAML files."""

	# NOTE: Borrowed from paml.engine
	SYMBOL_NAME    = "\??([\w\d_-]+::)?[\w\d_-]+"
	SYMBOL_ATTR    = "(%s)(=('[^']+'|\"[^\"]+\"|([^),]+)))?" % (SYMBOL_NAME)
	SYMBOL_ATTRS   = "^%s(,%s)*$" % (SYMBOL_ATTR, SYMBOL_ATTR)
	RE_ATTRIBUTE   = re.compile(SYMBOL_ATTR)

	LINES = {
		"onLinkTag"           : "^\t+<link\(",
		"onJavaScriptTag"     : "^\t+<script\(",
		"onJavaScriptRequire" : "^\t+@require\:js\(",
		"onJavaScriptGModule" : "^\t+@require\:gmodule\(",
		"onCSSRequire"        : "^\t+@require\:css\(",
		"onInclude"           : "^\t+%include\s*"
	}

	def _parseAttributes( self, attributes ):
		# NOTE: Borrowed and adapted from paml.engine.Parser._parsePAMLAttributes
		result   = []
		original = attributes
		while attributes:
			match  = self.RE_ATTRIBUTE.match(attributes)
			assert match, "Given attributes are malformed: %s" % (attributes)
			name  = match.group(1)
			value = match.group(4)
			# handles '::' syntax for namespaces
			name = name.replace("::",":")
			if value and value[0] == value[-1] and value[0] in ("'", '"'):
				value = value[1:-1]
			result.append([name, value])
			attributes = attributes[match.end():]
			if attributes:
				assert attributes[0] == ",", "Attributes must be comma-separated: %s" % (attributes)
				attributes = attributes[1:]
				assert attributes, "Trailing comma with no remaining attributes: %s" % (original)
		return dict((k,v) for k,v in result)

	def onLinkTag( self, line, match ):
		attrs = self._parseAttributes(line.split('(', 1)[-1].rsplit(")",1)[0])
		url = attrs.get("href")
		if attrs.get("rel") == "stylesheet" and url:
			if "://" in url:
				self.requires.append(("css:url",  url))
			else:
				self.requires.append(("css:file", url))

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

	def onCSSRequire( self, line, match ):
		return self.onJavaScriptRequire(line, match, type="css:module")

	def onInclude( self, line, match ):
		line = line[len(match.group()):]
		line = line.split("+",1)[0].split("{",1)[0].strip()
		if not os.path.splitext(line)[-1]: line += ".paml"
		type = "paml:file"
		if line.endswith(".svg"):
			type = "*:file"
		self.requires.append((type, line))

# -----------------------------------------------------------------------------
#
# PCSS PARSER
#
# -----------------------------------------------------------------------------

class PCSS(LineParser):
	"""Dependency parser for PCSS files."""

	OPTIONS = {}

	LINES = {
		"onModule"  : "^@module\s+([^\s]+)",
		"onInclude" : "^@include\s+([^\s]+)",
		"onImport"  : "^@@import\s+(.+)",
	}

	def onModule( self, line, match ):
		self.provides.append(("pcss:module",match.group(1)))

	def onInclude( self, line, match ):
		path = match.group(1).strip()
		self.requires.append(("pcss:file", self.normpath(path)))

	def onImport( self, line, match ):
		path = match.group(1).strip()
		if path[0] == path[-1] and path[0] in '"\'': path = path[1:-1]
		self.requires.append(("css:file", self.normpath(path)))

# -----------------------------------------------------------------------------
#
# DEPENDENCIES
#
# -----------------------------------------------------------------------------

class Tracker(object):
	"""Extracts and aggregates dependencies."""

	def __init__( self ):
		self.PARSERS = PARSERS
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

	def _fromPath( self, path, recursive=False, type=None ):
		"""Helper function of the `fromPath` method. Gets a parser
		for the given file type, parses the file at the given path and
		merges the `Parser.provides`/`Parser.requires`.
		"""
		if not os.path.exists(path) and "+" in path:
			paths  = path.split("+")
			prefix = os.path.dirname(paths[0])
			paths  = [paths[0]] + [os.path.join(prefix, _) for _ in paths[1:]]
			return [self._fromPath(_, recursive=recursive, item=item) for _ in paths]
		elif path in self.paths:
			return self
		elif os.path.isdir(path):
			# We skip directories
			pass
		else:
			# We add the path to prevent infinite recursion
			self.paths.append(path)
			# Now we find a parser for the extension
			ext         = path.rsplit(".",1)[-1].lower()
			parser_type = self.PARSERS.get(ext)
			# We return and log an error if there's no matching parser
			if not parser_type:
				logging.error("Parser not defined for type `{0}` in: {1}".format(ext, path))
				return
			# We do the parsing, merging back the provided and required elements.
			parser      = parser_type().parsePath(path, type=type)
			self.provides.append((path, parser.provides))
			self.requires = self._merge(self.requires, parser.requires)
			# We register/update the provided nodes
			for name in parser.provides:
				if name not in self.nodes: self.nodes[name] = []
				self.nodes[name] = self._merge(self.nodes[name], parser.requires)
			# We iterate on the dependency, trying to resolve them
			for dependency in parser.requires:
				# We don't resolve URLs (yet)
				dependency_type = dependency[0]
				if dependency_type.endswith(":url"):
					continue
				resolved = self.resolve(parser, dependency, path)
				if recursive:
					if not resolved:
						logging.error("Cannot recurse on {0} in {1}: dependency {0} cannot be resolved".format(dependency, path))
					for dependency_path in resolved:
						self._fromPath(dependency_path, recursive=recursive, type=dependency_type)

	def _merge( self, a, b ):
		for e in b:
			if e not in a:
				a.append(e)
		return a

	def resolve( self, parser, item, path ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		res = [_[1] for _ in parser.resolve(item, path)] or ()
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
			loaded.append(module)
			for required in self.nodes.get(module) or ():
				# NOTE: This is a bug, the modules should not import themselves
				if required == module: continue
				load(required, loaded)
			return loaded
		for _ in requires:
			load(_)
		return loaded

# -----------------------------------------------------------------------------
#
# RESOLVER
#
# -----------------------------------------------------------------------------

class Resolver(object):
	"""Resolves (symbol) names into files."""

	def __init__( self ):
		super(Resolver, self).__init__()
		self.PARSERS = PARSERS
		self.paths = []

	def addPath( self, path ):
		self.paths.append(path)
		return self

	def find( self, elements, path=None ):
		parsers = [(_, self.PARSERS[_]()) for _ in self.PARSERS]
		matches = {}
		path    = path or os.getcwd()
		if isinstance(elements, str) or isinstance(elements, unicode): elements=[elements]
		for element in elements:
			for t,p in parsers:
				matches.setdefault(element,[])
				# We ensure an element is not present twice
				for _ in p.resolve((None,element), path, self.paths):
					if _ not in matches[element]:
						matches[element].append(_)
		return matches

# -----------------------------------------------------------------------------
#
# PARSERS
#
# -----------------------------------------------------------------------------

PARSERS = {
	"paml" : Paml,
	"sjs"  : Sugar,
	"js"   : JavaScript,
	"pcss" : PCSS,
	"c"    : C,
	"cxx"  : C,
	"c++"  : C,
	"cpp"  : C,
	"h"    : C,
}

# -----------------------------------------------------------------------------
#
# COMMAND-LINE INTERFACE
#
# -----------------------------------------------------------------------------

def parse( path ):
	"""Tries to parse the file at the given path and return a list of
	the symbols that it provides as a couple `(type, [provides])`."""
	ext = path.rsplit(".", 1)[-1]
	parser = PARSERS.get(ext)
	if parser:
		parser = parser()
		return parser, parser.parsePath(path).export()
	else:
		return None, None

def provides( path ):
	"""Tries to parse the file at the given path and return a list of
	the symbols that it provides, if any."""
	parser, res = parse(path)
	return res["provides"] if res else ()

def find( args, recursive=True, resolve=False ):
	"""Lists all the dependencies listed in the given files."""
	rsl = Resolver()
	res = None
	if isinstance(args, str) or isinstance(args, unicode): args = [args]
	for _ in args:
		r = (rsl.find(_))
		if not res:
			res = r
		else:
			res.update(r)
	return res

def list( args, recursive=True, resolve=False ):
	"""Lists all the dependencies listed in the given files."""
	deps = Tracker()
	res  = {}
	if isinstance(args, str) or isinstance(args, unicode): args = [args]
	for _ in args:
		r = (deps.fromPath(_, recursive=recursive))
		if not res:
			res = r
		else:
			res.update(r)
	return res.get("requires") or ()

def run( args, recursive=False, mode=Tracker ):
	"""Extracts the dependencies of the given files."""
	if isinstance(args, str): args = [args]
	if mode == Tracker:
		deps = Tracker()
		res  = None
		for _ in args:
			r = (deps.fromPath(_, recursive=recursive))
			if not res:
				res = r
			else:
				res.update(r)
		return res
	elif mode == Resolver:
		res = find(args)
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
	oparser.add_argument("files", metavar="FILE", type=str, nargs='+',
			help='The files to extract dependencies from')
	oparser.add_argument("-o", "--output",    type=str,  dest="output", default="-",
			help="Specifies an output file")
	oparser.add_argument("-t", "--type",      type=str,  dest="types",  nargs="+", default=("*",),
			help="The types to be matched, wildcards accepted")
	oparser.add_argument("-r", "--recursive", dest="recursive",  action="store_true", default=False,
			help="Recurse through the dependencies")
	oparser.add_argument("-p", "--path",      dest="show_path",  action="store_true", default=False,
			help="Shows the relative path of the element")
	oparser.add_argument("-P", "--abspath",   dest="abs_path",   action="store_true", default=False,
			help="Shows the absolute path of the element")
	oparser.add_argument("-l", "--list",      dest="list",    action="store_true", default=False,
			help="Lists the dependencies of the given symbols (find mode)"
	)
	oparser.add_argument("-f", "--find",      dest="find",    action="store_true", default=False,
			help="Finds the files corresponding to the given symbols (find mode)"
	)
	# We create the parse and register the options
	args     = oparser.parse_args(args=args)
	out      = sys.stdout
	cwd      = os.getcwd()
	# === RESOLVER ============================================================
	# This runs like a first pass, as the resolved elements might be fed
	# to the dependency tracking, for instance:
	#
	# deparse -fl module
	# deparse -fr module
	#
	if args.find:
		# We're in resolution mode, so we're trying to locate the given elements
		res   = run(args.files, recursive=args.recursive, mode=Resolver)
		paths = []
		for name in args.files:
			resolved = sorted(set(res.get(name) or ()))
			groups = {}
			for t, path in resolved:
				groups.setdefault(path,[])
				groups[path].append(t)
			if not resolved:
				logging.error("Could not resolve: `{0}`".format(name))
			for path in sorted(groups.keys()):
				if args.show_path or args.abs_path:
					if path not in paths:
						if args.abs_path:
							out.write(os.path.abspath(n))
						else:
							out.write(n + ":")
							out.write(os.path.relpath(n,cwd))
						out.write("\n")
				elif not args.list or not args.recursive:
					out.write(name)
					out.write("\t")
					out.write(path)
					out.write("\t")
					out.write(",".join(groups.get(path)))
					out.write("\n")
				paths.append(path)
		if args.list or args.recursive:
			args.files = paths
	# === TRACKER =============================================================
	if not args.find or args.recursive or args.list:
		res = run(args.files, recursive=args.recursive, mode=Tracker)
		# We're in dependency mode, so we list the dependencies referenced
		# in the files given as arguments.
		resolved = []
		for item in res["requires"]:
			t, n = item
			for tp in args.types:
				if fnmatch.fnmatch(t, tp):
					if args.show_path or args.abs_path:
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
