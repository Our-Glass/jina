# File structure

Besides organizing your {class}`~jina.Executor` code inline, you can also write it as an "external" module and then use it via YAML. This is useful when your Executor’s logic is too complicated to fit into a single file.

```{tip}
The best practice is to use `jina hub new` to create a new Executor. It automatically generates the files you need in the correct structure.
```

## Single Python file + YAML

When you are only working with a single python file (let's call it `my_executor.py`), you can simply put it at the root of the repository, and import it directly in `config.yml`

```yaml
jtype: MyExecutor
py_modules:
  - my_executor.py
```

## Multiple Python files + YAML



When you are working with multiple python files, you should organize them as a **Python package** and put them in a special folder inside
your repository (as you would normally do with Python packages). Specifically, you should do the following:

- put all your Python files inside a special folder (call it `executor`, as a convention), and put an `__init__.py` file inside it
  - because of how Jina registers executors, make sure to import your executor in this file (see the contents of `executor/__init__.py` in the example below).
- use relative imports (`from .bar import foo`, and not `from bar import foo`) inside the python modules in this folder
- Only list `executor/__init__.py` under `py_modules` in `config.yml` - this way Python knows that you are importing a package, and makes sure that all the relative imports within your package work properly

To make things more specific, take this repository structure as an example:

```
.
├── config.yml
└── executor
    ├── helper.py
    ├── __init__.py
    └── my_executor.py
```

The contents of `executor/__init__.py` is

```python
from .my_executor import MyExecutor
```

the contents of `executor/helper.py` is

```python
def print_something():
    print('something')
```

and the contents of `executor/my_executor.py` is

```python
from jina import Executor, requests

from .helper import print_something


class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        print_something()
```

Finally, the contents of `config.yml` - notice that only the `executor/__init__.py` file needs to be listed under `py_modules`

```yaml
jtype: MyExecutor
py_modules:
  - executor/__init__.py
```

This was a relatively simple example, but this way of structuring python modules works for any python package structure, however complex. Consider this slightly more complicated example

```
.
├── config.yml           # Remains exactly the same as before
└── executor
    ├── helper.py
    ├── __init__.py
    ├── my_executor.py
    └── utils/
        ├── __init__.py  # Required inside all executor sub-folders
        ├── data.py
        └── io.py
```

Here you can then import from `utils/data.py` in `my_executor.py` like this: `from .utils.data import foo`, and do any other kinds of relative imports that python enables.

The best thing is that no matter how complicated your package structure, "importing" it in your `config.yml` file is super easy - you always put only `executor/__init__.py` under `py_modules`.
