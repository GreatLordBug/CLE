# CLE

CLE is a tiny language that compiles to Python and runs immediately.

## Quick start

From the project directory:

```bash
python3 compiler.py example.cle
```

This reads a `.cle` source file, translates it to Python in memory, and executes it.

## Core syntax

### Functions

```cle
func greet(name) ((
    tout("Hello, " + name)
    rvoid
))
```

A function body is wrapped in `(( ... ))` blocks.

### `tostart` and `ptstart`

`func tostart() (( ... ))` is required. It runs once before the main loop.

`func ptstart() (( ... ))` is optional. If it exists, the runtime calls it repeatedly until a `rvoid` ends the program.

### Variables

```cle
svar count = 0
slet name = "Ada"
```

- `svar` prints the assignment as it happens.
- `slet` declares a value without printing.
- All assignments inside functions should use `svar` or `slet`.

### Output and input

```cle
tout("Hello")
out = gin("Name? ")
```

The compiler aliases:

- `tout` -> `print`
- `gin` -> `input`

### Conditionals

```cle
if score > 10 ((
    tout("You win")
)) lif score == 10 ((
    tout("Draw")
)) els ((
    tout("You lose")
))
```

### Loops

```cle
for item in items ((
    tout(item)
))

while count < 3 ((
    tout(count)
    slet count = count + 1
))
```

### Returns

```cle
func add(a, b) ((
    rnum a + b
))

func greeting() ((
    rstr "hello"
))
```

Supported return forms include:

- `rstr`
- `rnum` for int or float
- `rint`
- `rfloat`
- `rlist`
- `rbool`
- `rvoid`

### Imports

`import` is intentionally unsupported in CLE.

## Example programs

- `example.cle` shows a small multi-function demo
- `example2.cle` is a simple hangman game

## Notes

- CLE uses Python-like expressions and literals.
- Top-level statements are limited to variable declarations.
- Function bodies must be written with the `(( ... ))` syntax.
- `import` does not exist in CLE.
