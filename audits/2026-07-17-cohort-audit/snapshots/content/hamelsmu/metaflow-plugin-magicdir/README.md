# Magic Directories

An experimental plugin for passing data in directories in between steps.

**Warning: this package is highly experimental.**

## Installation

```bash
pip install metaflow-plugin-magicdir
```

## Usage

You can use `@magicdir` to pass local directories between metaflow steps.  This will also work remotely.

```py
#flow.py
from metaflow import FlowSpec, step
from metaflow.plugins import magicdir

class MagicDirFlow(FlowSpec):

    @magicdir(dir='mydir')
    @step
    def start(self):
        with open('mydir/output1', 'w') as f:
            f.write('hello world')
        with open('mydir/output2', 'w') as f:
            f.write('hello world again')
        self.next(self.end)

    @magicdir(dir='mydir')
    @step
    def end(self):
        print('first', open('mydir/output1').read())
        print('second', open('mydir/output1').read())

if __name__ == "__main__":
    MagicDirFlow()
```

If you run the above flow, you will see the following output:

```bash
> python flow.py run --with batch

2022-02-05 12:49:51.503 Workflow starting (run-id 11):
2022-02-05 12:49:51.511 [11/start/1 (pid 65038)] Task is starting.
2022-02-05 12:49:52.157 [11/start/1 (pid 65038)] Task finished successfully.
2022-02-05 12:49:52.165 [11/end/2 (pid 65046)] Task is starting.
2022-02-05 12:49:52.724 [11/end/2 (pid 65046)] first hello world
2022-02-05 12:49:52.799 [11/end/2 (pid 65046)] second hello world
2022-02-05 12:49:52.800 [11/end/2 (pid 65046)] Task finished successfully.
2022-02-05 12:49:52.801 Done!
```

### `magicdir` with `foreach`

Nothing special is required to use `magicdir` with foreach.  Consider the following modification to the above flow:

```py
#mapflow.py

from metaflow import FlowSpec, step
from metaflow.plugins import magicdir


class MagicDirMapFlow(FlowSpec):
    """Show how magic directories work with foreach"""

    @step
    def start(self):
        self.step_num = range(5)
        self.next(self.write, foreach='step_num')

    @magicdir(dir='my_map_dir')
    @step
    def write(self):
        self.step_idx = self.input # metaflow gives self.input a value from `step_num` from the prior step
        with open(f'my_map_dir/o.txt', 'w') as f:
            f.write(f'this is step {self.step_idx}')
        self.next(self.read)

    @magicdir(dir='my_map_dir')
    @step
    def read(self):
        print('file contents:', open(f'my_map_dir/{self.step_idx}.txt').read())
        self.next(self.join)
    
    @step
    def join(self, inputs):
        print(f"step numbers were: {[i.step_idx for i in inputs]}")
        self.next(self.end)

    @step
    def end(self): pass

if __name__ == "__main__":
    MagicDirMapFlow()
```

If you execute this flow, you will see an output like this:

```
> python mapflow.py run
2022-02-05 13:52:37.475 Workflow starting (run-id 12):
2022-02-05 13:52:37.482 [12/start/1 (pid 74801)] Task is starting.
2022-02-05 13:52:38.116 [12/start/1 (pid 74801)] Foreach yields 5 child steps.
2022-02-05 13:52:38.116 [12/start/1 (pid 74801)] Task finished successfully.
2022-02-05 13:52:38.124 [12/write/2 (pid 74806)] Task is starting.
2022-02-05 13:52:38.132 [12/write/3 (pid 74807)] Task is starting.
2022-02-05 13:52:38.140 [12/write/4 (pid 74808)] Task is starting.
2022-02-05 13:52:38.147 [12/write/5 (pid 74809)] Task is starting.
2022-02-05 13:52:38.156 [12/write/6 (pid 74810)] Task is starting.
2022-02-05 13:52:38.902 [12/write/2 (pid 74806)] Task finished successfully.
2022-02-05 13:52:38.912 [12/read/7 (pid 74824)] Task is starting.
2022-02-05 13:52:38.925 [12/write/3 (pid 74807)] Task finished successfully.
2022-02-05 13:52:38.933 [12/read/8 (pid 74825)] Task is starting.
2022-02-05 13:52:38.935 [12/write/4 (pid 74808)] Task finished successfully.
2022-02-05 13:52:38.935 [12/write/6 (pid 74810)] Task finished successfully.
2022-02-05 13:52:38.936 [12/write/5 (pid 74809)] Task finished successfully.
2022-02-05 13:52:38.944 [12/read/9 (pid 74826)] Task is starting.
2022-02-05 13:52:38.951 [12/read/10 (pid 74827)] Task is starting.
2022-02-05 13:52:38.959 [12/read/11 (pid 74828)] Task is starting.
2022-02-05 13:52:39.616 [12/read/7 (pid 74824)] file contents: this is step 0
2022-02-05 13:52:39.670 [12/read/9 (pid 74826)] file contents: this is step 2
2022-02-05 13:52:39.673 [12/read/10 (pid 74827)] file contents: this is step 4
2022-02-05 13:52:39.673 [12/read/8 (pid 74825)] file contents: this is step 1
2022-02-05 13:52:39.673 [12/read/11 (pid 74828)] file contents: this is step 3
2022-02-05 13:52:39.717 [12/read/7 (pid 74824)] Task finished successfully.
2022-02-05 13:52:39.779 [12/read/8 (pid 74825)] Task finished successfully.
2022-02-05 13:52:39.783 [12/read/10 (pid 74827)] Task finished successfully.
2022-02-05 13:52:39.784 [12/read/9 (pid 74826)] Task finished successfully.
2022-02-05 13:52:39.785 [12/read/11 (pid 74828)] Task finished successfully.
2022-02-05 13:52:39.792 [12/join/12 (pid 74839)] Task is starting.
2022-02-05 13:52:40.378 [12/join/12 (pid 74839)] step numbers were: [2, 3, 0, 4, 1]
2022-02-05 13:52:40.451 [12/join/12 (pid 74839)] Task finished successfully.
2022-02-05 13:52:40.459 [12/end/13 (pid 74842)] Task is starting.
2022-02-05 13:52:41.103 [12/end/13 (pid 74842)] Task finished successfully.
2022-02-05 13:52:41.104 Done!
```


