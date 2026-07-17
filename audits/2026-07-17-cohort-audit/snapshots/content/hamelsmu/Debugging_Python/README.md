# Debugging In Python
Notes to myself in how to effectively debug in python not relying on an IDE like PyCharm.


**Option 1:** Do this without any additional code.  For some reason, you will have to press `c` to get the program to continue to the right place:

` $ python -m ipdb cli_debugflag.py`
```
 ipdb> c

 > /Users/hamelhusain/GHRepos/Debugging_Python/cli_debugflag.py(8)testfunc()
      6
      7 def testfunc(p1, p2):
----> 8     return p1 + p2
      9

ipdb>
```
---

**Option 2:** Execute your code under `with launch_ipdb_on_exception():`
However, since you don't want this shell to execute if you are running this script on a production environment you should allow the user the specify a debug mode.  *I designed this via a CLI* using the `click` library, as demonstrated in `cli_debug.py`.   To see how this work run

`$ python cli_debug.py --debug`

---
**Option 3:** Drop the following line in your code:
```
import ipdb
ipdb.set_trace()
ipdb.set_trace(context=5)  # will show five lines of code
                           # instead of the default three lines
```
---
**Option 4:** use `post_mortem()`.  This looks like the cleanest method.  This command is the equivalent of running `%debug` in a jupyter notebook.  See `cli_debugsimple.py`  .  Just like before, made file to accept --debug flag on the CLI as we don't want to cause problems if this is running in production. Some tips:

  - there is also a method called `pm()` but `post_mortem()` seems to work better.  
  - you must put post_mortem in a `try ... except` block, for it to work.  See the design pattern in `cli_debugsimple.py`, its helpful to still invoke `raise` even if the debug flag is not on so that the error is still printed to stdout.

`$ python cli_debugsimple.py --debug`

```
 /Users/hamelhusain/GHRepos/Debugging_Python/cli_debugsimple.py(8)testfunc()
      6
      7 def testfunc(p1, p2):
----> 8     return p1 + p2
      9

ipdb>
```


### Other Links
[Debugging Like a Boss](https://zapier.com/engineering/debugging-python-boss/) : this has alternative debuggers like pudb

[ipdb repo](https://github.com/gotcha/ipdb)
