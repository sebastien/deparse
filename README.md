deparse ― multi-language dependency parsing
===========================================

```
         __                              
    ____/ /__  ____  ____ ______________ 
   / __  / _ \/ __ \/ __ `/ ___/ ___/ _ \
  / /_/ /  __/ /_/ / /_/ / /  (__  )  __/
  \__,_/\___/ .___/\__,_/_/  /____/\___/ 
           /_/                           

```

*Deparse* is both a command-line tool and Python module to parse and list
dependencies in a language-independent way.

```shell
$ deparse lib/js/*.js
```

Language support:

- C (non-recursive)
- JS (UMD, AMD, CommonJS, Google) (non-recursive)
- [Paml](https://github.com/sebastien/paml)
- [Sugar](https://github.com/sebastien/sugar)

Features:

- Optional **recursive dependency tracking**
- Dependencies are **sorted based on load order**
- Pluggable name-to-path resolution scheme
- Extensible to other languages

Installing
==========

*Deparse* is available on [PyPI](https://pypi.python.org/pypi/deparse) and 
supports both Python 2 and 3.

```shell
pip install deparse
```

This installs the *deparse* module and the `deparse` command:

```shell
$ deparse --help
usage: deparse [-h] [-o OUTPUT] [-t TYPES [TYPES ...]] [-r] [-p]
               FILE [FILE ...]

Lists dependencies from PAML and Sugar files

positional arguments:
  FILE                  The files to extract dependencies from

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
  -t TYPES [TYPES ...], --type TYPES [TYPES ...]
  -r, --recursive
  -p, --path
```

Examples
========

- **Listing per-file dependencies in a makefile**
- **Create arguments for `closure-compiler`**


Planned features
================

- [ ] Dot/Neato output
- [ ] CSS, PCSS support
- [ ] Customisable resolution schemes
