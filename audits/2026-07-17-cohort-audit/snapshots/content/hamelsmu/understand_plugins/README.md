# Python Plugin Notes

## What is a plugin?

[Plugins](https://en.wikipedia.org/wiki/Plug-in_(computing)) are a way to add additoinal functionality to a python package without interfering with the main package.  For example, the [datasette project has plugins](https://docs.datasette.io/en/stable/plugins.html) for various types of additional functionality.  Plugins are useful when:

- You want to keep the main package clean and simple, but allow people to install more things depending on the features they desire.
- Make your package more extensible.  You can add more functionality to your package without having to change the main package.
- Provide a way for third parties to create add-ons to your package.

## Background

This repo contains a minimal python package and two plugins to understand how python plugins work.  I was reading about the [different ways to create plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) and decided to try out the [namespace](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/) approach.  

I found the documentation to be confusing, so I decided to create a minimal example to clarify things for me.

## Instructions

Install the main package and the two plugins:

```py
cd main_package
pip install .
cd ../plugin_1/
pip install .
cd ../plugin_2/
pip install .
```

After you do this, you can test that the plugins are available as follows.  **Warning, plugins are not loaded into the ipython shell until you import them in a fully qualified way (they do not appear in `dir()` so you can get false import errors if you do not do this).** 

```py
# the plugin that is in the main package
>>> from fake_package.plugins import ns_pkg
'this is the ns pkg in the main pkg'

# plugin_1
>>> from fake_package.plugins import a
>>> a()
'wohoo you have a plugin!'

# plugin_2
>>> from fake_package.plugins.plugin_b import b
>>> b()
'wohoo you have a different plugin!'
```
