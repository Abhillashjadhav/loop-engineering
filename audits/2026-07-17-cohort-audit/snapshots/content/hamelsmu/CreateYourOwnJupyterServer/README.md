# Step 1: Add shortcuts to your local instance for SSH

-  On MacOSX, Open your `.bash_profile` and place an alias in there like this
```
alias jupssh="ssh -L 7654:localhost:7654 some-computer.net"
```
This sets up port forwarding so that your remote jupyter server will forward traffic to your local computer.  *On Mac, you can find your bash_profile at `~/.bash_profile`*

- Still on your Mac, Load your bash_profile. In terminal:
> source ~/.bash_profile

# Step 2: Login To Remote Machine & Install Byobu
- login to remote server with the alias you just created!, In Terminal
> jupssh

- install byobu on remote machine
> sudo apt-get install byobu; byobu-enable;

  Takes a bit getting used to but isn't bad at all. [see common hotkeys](https://medium.com/russian-it-stories/byobu-cheatsheet-%D0%BCost-used-hotkeys-5a8bbd8476fd)

# Step 3: Install Anaconda on Remote Machine

- Download Anaconda - get link from [here](https://www.anaconda.com/download/#linux), use wget. Example:
> wget https://repo.continuum.io/archive/Anaconda3-5.0.1-Linux-x86_64.sh


- Install Anaconda From file you just downloaded
> sudo bash Anaconda3-5.0.1-Linux-x86_64.sh -b -p $HOME/anaconda3

      the `-b` flag just means ignore prompts and you agree to the license

      the `-p` flag allows you to specify where you want to install Anaconda

- Add Anaconda to your python path. Open your bashrc file, and add the following line to the end of the file:
> export PATH=$HOME/anaconda3/bin:$PATH

- Check that it was added correctly
> which python
/home/hamelsmu/anaconda3/bin/python

# Step 4: Start Jupyter Notebook:
- Change `your_password` with your own personal password

> jupyter notebook --no-browser --port=7654 --NotebookApp.token='your_password'

# Step 5: Enjoy Jupyter Server On Local Computer
- Navigate to http://localhost:7654/ in your browser
