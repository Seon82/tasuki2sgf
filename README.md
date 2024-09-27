# tasuki2sgf

This project is a simple python script that can be used to generate `.sgf` files from [tasuki's tsumego collection](https://tsumego.tasuki.org/), as a good part of the original sources have been lost to time.

To do so, we simply parse the `.tex` files used to generate the pdf versions of the problems.


## Usage

This code requires `python3`.

Put the `.tex` files [found here](https://github.com/tasuki/tsumego/tree/master/books/problems) in a directory named `tex_files`, then run :
```bash
python3 tex_files --output sgf_files
```
You can normalize the problems so black always go first, by adding the`--normalize` flag to the above command. 

You can also generate `.svg` images of each problem by adding the `--render` flag to the command. You'll need to install [sgf-render](https://github.com/julianandrews/sgf-render) for this to work. 

