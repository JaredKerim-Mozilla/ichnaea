.. _development:

===========
Development
===========

Documentation
-------------

In order to create and test the documentation locally run:

.. code-block:: bash

    make docs

The documentation will be available in ``docs/build/html/index.html``.


Python Dependencies
-------------------

The project uses `requires.io <https://requires.io/github/mozilla/ichnaea/requirements/?branch=master>`_ 
to track whether or not the Python dependencies are outdated.

If they are, update the version pins in the various `requirements/*.txt`
files and rerun `make`, `make docs` or `make test`, depending on which
requirements have changed.


CSS / JS / Images
-----------------

The project depends on a number of external web assets. Those dependencies
are tracked via npm and bower.

In order to install them, run:

.. code-block:: bash

    make css
    make js

This will install a couple of build tools under `node_modules` and various
assets under `bower_components`. It will also copy, compile and minify
files into various folders under `ichnaea/content/static/`.

To check if the external assets are outdated run:

.. code-block:: bash

    ./node_modules/.bin/bower list

To force-update the build tools run:

.. code-block:: bash

    make node_modules -B


Cleanup
-------

In case the local environment gets into a weird or broken state, it can
be cleaned up by running:

.. code-block:: bash

    make clean

Of course one can also delete the entire git repository and start from
a fresh checkout.


Release Build
-------------

The default `make` / `make build` target installs a local development
version including database setup and testing tools. For a production
environment or release pipeline one can instead use:

.. code-block:: bash

    make release

This will not do any database setup and only install production
dependencies. It will also create a virtualenv and install the ichnaea
code itself via `bin/python setup.py install`, so that a copy will be
installed into `lib/pythonX.Y/site-packages/`.

The step will also compile all py files to pyc files and remove any files
from the tree which aren't compatible with the active Python version
(blacklist in the `compile.py` script). The removal step ensures that
any build tools (for example rpmbuild / mock) that typically call
`compileall.compile_dir` will work, without breaking on the incompatible
files.
