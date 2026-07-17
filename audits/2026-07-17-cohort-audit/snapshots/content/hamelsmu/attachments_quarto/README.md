# attachments_quarto

## Issue:

Cell attachments are rendered by Quarto properly w/ Jupyter Lab but not Jupyter Classic

To reproduce this error:

1. Clone [this repo](https://github.com/hamelsmu/attachments_quarto), which is an minimal quarto project
2. Run quarto preview
3. Start **Jupyter Lab**, and in `nb.ipynb` add different cell attachments by taking several screenshots and pasting them into markdown cells directly.  Everything works in Quarto :tada:
4. Start **A Classic Jupyter Notebook (not Jupyter Lab)**, and do the same thing re: cell attachments in `nb-classic.ipynb`, Quarto will repeat the first cell attachment across all of them. 

Upon some investigation, it does indeed appear that Jupyter Lab and Jupyter Classic handle cell attachments differently, which could be causing the issue.  

### Questions:
1. Is Jupyter Classic supported in Quarto?
2. Is this something that is possible to fix?


