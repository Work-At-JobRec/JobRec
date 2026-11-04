import json
from sys import argv

with open(argv[1]) as infile:
    input: dict = json.load(infile)

with open(argv[2], "wt") as outfile:
    for k, v in input.items():
        outfile.write(f"{k}={v}\n")
