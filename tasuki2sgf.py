import argparse
import json
import re
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal, Optional, Set, Tuple


class SimpleSGF:
    """
    A tiny SGF parser.

    Supports the bare minimum necessary to read tasuki's tsumegos,
    aka static boards with labels and a comment.
    """

    def __init__(self, size: int = 19):
        self.size: int = size
        self.setup_black: Set[Tuple[int, int]] = set()
        self.setup_white: Set[Tuple[int, int]] = set()
        self.marks: Set[Tuple[str, int, int]] = set()
        self.comment: Optional[str] = None
        self.player: Literal["B", "W"] = "B"

    def coord2letter(self, row: int, col: int) -> str:
        """
        Convert a row/col pair to SGF letter codes.
        """
        return chr(col + 97) + chr(self.size - row - 1 + 97)

    def set_setup_stones(
        self, black: Iterable[Tuple[int, int]], white: Iterable[Tuple[int, int]]
    ):
        """
        Set the initial stone configuration on the board.
        """
        self.setup_black = set(black)
        self.setup_white = set(white)

    def add_label(self, label: str, row: int, col: int):
        """
        Add a label to one of the board's intersections.
        """
        self.marks.add((label, row, col))

    def set_comment(self, comment: str):
        """
        Set a general comment for the board.
        """
        self.comment = comment

    def set_player(self, player: Literal["B", "W"]):
        """
        Set the color of the player that starts.
        """
        assert player.upper() in "BW"
        self.player = player.upper()

    def flip_colors(self):
        """
        Flip black and white.
        """
        self.setup_black, self.setup_white = self.setup_white, self.setup_black
        if self.player == "B":
            self.player = "W"
        if self.player == "W":
            self.player == "B"

    def serialize(self) -> bytes:
        """
        Serialize to utf-8.
        """
        buffer = ";FF[4]GM[1]"
        buffer += f"SZ[{self.size}]"
        if self.comment:
            buffer += f"\nC[{self.comment}]"
        if self.player:
            buffer += f"\nPL[{self.player}]"
        if self.setup_black:
            buffer += "\nAB" + "".join(
                f"[{self.coord2letter(*x)}]" for x in self.setup_black
            )
        if self.setup_white:
            buffer += "\nAW" + "".join(
                f"[{self.coord2letter(*x)}]" for x in self.setup_white
            )
        if self.marks:
            buffer += "\nLB" + "".join(
                f"[{self.coord2letter(x[1], x[2])}:{x[0]}]" for x in self.marks
            )
        buffer += "\nCA[UTF-8]"

        buffer = f"({buffer})\n"
        return buffer.encode("utf-8")


def tex2sgf(tex: str) -> SimpleSGF:
    """
    Parse a string representing a tex board to a SimpleSGF.

    The string should represent a board using gooe, and have line breaks
    at the end of each line.
    """
    lines = (
        tex.replace(r"\0??", "").replace(r"\- ", "").replace(r"\!  ", "").split("\n")
    )

    game = SimpleSGF(size=19)
    setup = {"black": [], "white": []}
    for row_num, row in enumerate(lines):
        col_num = 0
        for symbol in row:
            if symbol in "A-Z":
                game.add_label(symbol, game.size - 1 - row_num, col_num)
            if symbol in "@!":
                mapping = {"@": "black", "!": "white"}
                setup[mapping[symbol]].append((game.size - 1 - row_num, col_num))
            else:
                col_num += 1
    game.set_setup_stones(black=setup["black"], white=setup["white"])
    return game


class ShrinkWrapOption(Enum):
    NO = 0
    YES = 1
    ROW_ONLY = 2


def render_sgf(
    game: SimpleSGF,
    output_filename: str | Path,
    shrink_wrap: ShrinkWrapOption = ShrinkWrapOption.NO,
):
    """Render a SimpleSGF to a svg file."""

    # Sgf-render needs an on-disk input file, so we dump
    # the game to a temp file we delete at the end of the function call
    temp = tempfile.NamedTemporaryFile(mode="wb", delete_on_close=False)
    temp.write(game.serialize())
    temp.close()
    cmd = [
        "sgf-render",
        temp.name,
        "--style",
        "minimalist",
        "--no-board-labels",
        "-o",
        output_filename,
    ]
    if shrink_wrap == ShrinkWrapOption.YES:
        cmd.append("-s")
    elif shrink_wrap == ShrinkWrapOption.ROW_ONLY:
        moves = game.setup_black | game.setup_white
        min_row = min(moves, key=lambda x: x[0])[0]
        vw = f"aa-s{min(chr(game.size - min_row + 97 ), 's')}"
        cmd.extend(["-r", vw])
    subprocess.call(cmd)
    # If svgcleaner is installed, minify generated svg files
    if shutil.which("svgcleaner"):
        subprocess.call(["svgcleaner", "--quiet", output_filename, output_filename])
    # Delete the temp file
    Path(temp.name).unlink()


def extract_sgf(
    tex_filename: str | Path,
    sgf_output_dir: str | Path,
    render_output_dir: str | Path | None = None,
    filename: str = "{name} - (problem {problem_num})",
    normalize: bool = False,
):
    """
    Generate and render sgfs from a tex file.

    Args:
        tex_filename: the path to the tex file to process.
        sgf_output_dir: the directory the extracted sgf files should be saved to.
        render_output_dir: the directory the rendered sgf files should be saved to.
                            Set to None to disable rendering.
        filename: the name format used to name the sgf and rendered svg files.
        normalize: set to True to modify the sgf's so that it's always black's turn to play.
    """
    with open(tex_filename, "r") as f:
        content = f.read()

    # Sanitize input
    sgf_output_dir = Path(sgf_output_dir)
    if render_output_dir is not None:
        render_output_dir = Path(render_output_dir)

    # Iterate over go problems
    all_matches = re.finditer(
        r"^\\vbox{\\vbox{\\goo\n([\s\S]*?)\}", content, flags=re.MULTILINE
    )
    all_names = re.finditer(r"^\\hfil(.*)\\hfil", content, flags=re.MULTILINE)
    for i, (match_board, match_title) in enumerate(zip(all_matches, all_names)):
        # Extract and save sgf
        name = match_title.group(1).strip()
        game = tex2sgf(match_board.group(1))
        if "white to play" in name:
            game.set_player("W")
            if normalize:
                name = (
                    name.replace("black", "!!temp")
                    .replace("white", "black")
                    .replace("!!temp", "white")
                )
                # Remove "black to play" in name if it's never white to play
                if name.endwith("black to play"):
                    name.replace(", black to play", "")
                game.flip_colors()
        game.set_comment(name)
        sgf_filename = sgf_output_dir / (
            filename.format(problem_num=i + 1, name=name) + ".sgf"
        )
        with open(sgf_filename, "wb") as f:
            f.write(game.serialize())
        # Save svg if render_output_dir is specified
        if render_output_dir is not None:
            svg_filename = render_output_dir / (
                filename.format(problem_num=i + 1, name=name) + ".svg"
            )
            render_sgf(
                game,
                svg_filename,
                shrink_wrap=ShrinkWrapOption.ROW_ONLY,
            )


def merge_sgfs(
    sgf_dir: Path | str, output_file: Path | str, comment: Optional[str] = ""
):
    """
    Merge all SGF files in sgf_dir into output_file.

    The input SGFs MUST have been created using extract_sgf.
    """
    all_games = f"(;FF[4]GM[1]SZ[19]\nC[{comment}]"
    for file in sorted(
        Path(sgf_dir).glob("*.sgf"),
        key=lambda p: [int(x) for x in re.findall(r"\d+", str(p.stem))],
    ):
        with open(file, "r") as f:
            game = f.read()
            game = "".join(game.split("\n")[1:-2])
            game = f"(;{game})"
            all_games += "\n" + game
    all_games += "\n)"
    with open(output_file, "w") as f:
        f.write(all_games)


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="A simple tool to extract tasuki's tsumegos."
    )

    parser.add_argument(
        "--render",
        action="store_true",  # Default to False
        help="Render the extracted sgf files to svg. Requires sgf-render.",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",  # Default to False
        help="Normalize tsumegos so it's always black to play.",
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="The input directory path, containing the tex files to process.",
    )

    # Add output dir argument with default value
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=Path("./output"),
        help="The output directory path (default: ./output).",
    )

    # Parse the arguments
    args = parser.parse_args()

    with open("comments.json", "r") as f:
        file2comment = json.load(f)

    # Check if input_dir exists
    if not args.input_dir.exists():
        print(f"Input directory '{args.input_dir}' does not exist.")
        return

    if args.render and not shutil.which("sgf-render"):
        print("sgf-render is not available, not rendering svg files.")
        args.render = False

    for file in args.input_dir.glob("*.tex"):
        print("Processing", file)
        output_dir: Path = args.output_dir / file.stem
        output_dir.mkdir(exist_ok=True, parents=True)
        sgf_output_dir = output_dir / "sgf"
        sgf_output_dir.mkdir(exist_ok=True)
        if args.render:
            render_output_dir = output_dir / "render"
            render_output_dir.mkdir(exist_ok=True)
        else:
            render_output_dir = None
        # Generate individual SGF files
        extract_sgf(
            tex_filename=file,
            sgf_output_dir=sgf_output_dir,
            render_output_dir=render_output_dir,
            filename="{name}",
            normalize=False,
        )
        # Create an all-in-one sgf file
        merge_sgfs(
            sgf_output_dir,
            output_dir / (file.stem + ".sgf"),
            comment=file2comment.get(file.stem, ""),
        )


if __name__ == "__main__":
    main()
