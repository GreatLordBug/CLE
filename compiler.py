from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class CLECompileError(SyntaxError):
	pass


class _CLEProgramExit(Exception):
	pass


class _CLEReturnTypeError(TypeError):
	pass


def _cle_svar(name, value):
	print(f"{name} = {value}")
	return value


def _cle_return(value, expected, line):
	if expected is not None and not isinstance(value, expected):
		expected_name = "number" if expected == (int, float) else expected.__name__
		raise _CLEReturnTypeError(
			f"CLE line {line}: expected {expected_name}, got {type(value).__name__}"
		)
	return value


def _cle_checked(function):
	annotations = function.__annotations__
	names = list(function.__code__.co_varnames[: function.__code__.co_argcount])

	def checked(*args, **kwargs):
		values = dict(zip(names, args))
		values.update(kwargs)
		for name, expected in annotations.items():
			if name in values and isinstance(expected, type) and not isinstance(values[name], expected):
				raise TypeError(
					f"CLE parameter {name!r} expected {expected.__name__}, "
					f"got {type(values[name]).__name__}"
				)
		return function(*args, **kwargs)

	checked.__name__ = function.__name__
	return checked


def _error(path, line_number, message, column=1):
	raise CLECompileError(f"{path}:{line_number}:{column}: {message}")


def _strip_comment(line):
	quote = None
	escaped = False
	index = 0
	while index < len(line) - 1:
		char = line[index]
		if escaped:
			escaped = False
		elif char == "\\" and quote:
			escaped = True
		elif char in "'\"" and not quote:
			quote = char
		elif char == quote:
			quote = None
		elif char == "/" and line[index + 1] == "/" and not quote:
			return line[:index].rstrip()
		index += 1
	return line.rstrip()


def _split_closing(line):
	match = re.match(r"^(\s*)\)\)\s+(lif\b.*|els\b.*)$", line)
	if match:
		return [match.group(1) + "))", match.group(1) + match.group(2)]
	return [line]


def _translate_header(text, path, line_number):
	if "((" not in text:
		_error(path, line_number, "block header must end with ((")
	header = text[: text.index("((")].rstrip()
	if header.startswith("func "):
		match = re.fullmatch(r"func\s+([A-Za-z_]\w*)\s*\((.*)\)", header)
		if not match:
			_error(path, line_number, "invalid func declaration")
		return f"@_cle_checked\ndef {match.group(1)}({match.group(2)}):"
	if header.startswith("if "):
		return f"if {header[3:].strip()}:"
	if header.startswith("lif "):
		return f"elif {header[4:].strip()}:"
	if header == "els":
		return "else:"
	if header.startswith("while "):
		return f"while {header[6:].strip()}:"
	if header.startswith("for "):
		return f"{header}:"
	_error(path, line_number, f"unknown block header: {header}")


def _translate_statement(text, path, line_number, function_name):
	if text.startswith("import ") or text == "import":
		_error(path, line_number, "import is not supported in CLE")
	if text.startswith("function "):
		_error(path, line_number, "use func, not function")
	if text in {"brk", "con"}:
		return "break" if text == "brk" else "continue"
	if text == "rvoid":
		return "raise _CLEProgramExit" if function_name == "ptstart" else "return"

	return_match = re.fullmatch(r"r(\w+)\s+(.+)", text)
	if return_match:
		type_name, expression = return_match.groups()
		expected = {
			"int": "int",
			"float": "float",
			"str": "str",
			"list": "list",
			"dict": "dict",
			"bool": "bool",
			"num": "(int, float)",
			"any": "None",
		}.get(type_name)
		if expected is None:
			_error(path, line_number, f"unknown return type: r{type_name}")
		return f"return _cle_return({expression}, {expected}, {line_number})"

	declaration = re.fullmatch(
		r"(svar|slet)\s+([A-Za-z_]\w*)(?:\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*))?\s*=\s*(.+)",
		text,
	)
	if declaration:
		keyword, name, annotation, expression = declaration.groups()
		annotation_text = f": {annotation}" if annotation else ""
		assignment = f"{name}{annotation_text} = {expression}"
		if keyword == "svar":
			assignment += f"\n_cle_svar({name!r}, {name})"
		return assignment

	if re.match(r"[A-Za-z_]\w*\s*(?:\[[^]]+\])?\s*(?:=|\*=|/=)", text):
		_error(path, line_number, "assignments must use svar or slet")
	shorthand = re.match(r"^(tout|gin)\s+(.+)$", text)
	if shorthand and not shorthand.group(2).startswith("("):
		return f"{shorthand.group(1)}({shorthand.group(2)})"
	return text


def compile_source(source, path="<string>"):
	generated = [
		"# Generated from CLE",
		"",
		"tout = print",
		"gin = input",
		"",
	]
	top_level_names = set()
	function_stack = []
	function_global_declared = {}
	saw_tostart = False
	block_depth = 0
	in_docstring = False
	docstring_lines = set()

	raw_lines = []
	for number, original in enumerate(source.splitlines(), 1):
		line = _strip_comment(original)
		if not line.strip():
			continue
		if "***" in line:
			line = line.replace("***", '"""')
			docstring_lines.add(number)
			in_docstring = not in_docstring
		elif in_docstring:
			docstring_lines.add(number)
		raw_lines.extend((number, part) for part in _split_closing(line))

	for line_number, line in raw_lines:
		source_indent = len(line) - len(line.lstrip(" "))
		text = line.strip()
		if text == "))":
			if block_depth == 0:
				_error(path, line_number, "unexpected ))")
			if generated and generated[-1].rstrip().endswith(":"):
				generated.append(" " * (source_indent + 4) + "pass")
			block_depth -= 1
			if function_stack and source_indent <= function_stack[-1][0]:
				function_stack.pop()
			continue

		if "((" in text:
			translated = _translate_header(text, path, line_number)
			if translated.startswith("@_cle_checked"):
				if len(function_stack) >= 3:
					_error(path, line_number, "nested functions may not exceed three levels")
				generated.append(" " * source_indent + "@_cle_checked")
				translated = translated.splitlines()[1]
				function_name = re.match(r"def\s+(\w+)", translated).group(1)
				if function_name == "tostart":
					saw_tostart = True
				function_stack.append((source_indent, function_name))
				function_global_declared[function_name] = False
			generated.append(" " * source_indent + translated)
			if function_stack and top_level_names and not function_global_declared.get(function_stack[-1][1], False):
				generated.append(" " * (source_indent + 4) + "global " + ", ".join(sorted(top_level_names)))
				function_global_declared[function_stack[-1][1]] = True
			block_depth += 1
			continue

		current_function = function_stack[-1][1] if function_stack else None
		is_docstring = line_number in docstring_lines or text.startswith(('"""', "'''"))
		if current_function is None and not is_docstring and not text.startswith("#"):
			if not re.match(r"(?:svar|slet)\b", text):
				_error(path, line_number, "only svar/slet declarations are allowed at top level")
			decl_match = re.fullmatch(r"(?:svar|slet)\s+([A-Za-z_]\w*)\b.*", text)
			if decl_match:
				top_level_names.add(decl_match.group(1))
		translated = _translate_statement(text, path, line_number, current_function)
		for translated_line in translated.splitlines():
			generated.append(" " * source_indent + translated_line)

	if block_depth:
		_error(path, len(source.splitlines()) or 1, "unclosed (( block")
	if not saw_tostart:
		_error(path, 1, "tostart must be declared")

	generated.extend(
		[
			"",
			"try:",
			"    tostart()",
			"    while True:",
			"        if 'ptstart' not in globals():",
			"            break",
			"        ptstart()",
			"except _CLEProgramExit:",
			"    pass",
		]
	)
	return "\n".join(generated) + "\n"


def run_file(path):
	source_path = Path(path)
	if source_path.suffix != ".cle":
		raise CLECompileError(f"expected a .cle file, got {source_path.name}")
	generated = compile_source(source_path.read_text(encoding="utf-8"), str(source_path))
	namespace = {
		"_CLEProgramExit": _CLEProgramExit,
		"_CLEReturnTypeError": _CLEReturnTypeError,
		"_cle_return": _cle_return,
		"_cle_svar": _cle_svar,
		"_cle_checked": _cle_checked,
	}
	try:
		exec(compile(generated, str(source_path), "exec"), namespace, namespace)
	except CLECompileError:
		raise
	except Exception as error:
		raise RuntimeError(f"{source_path}: runtime error: {error}") from error


def main(argv=None):
	parser = argparse.ArgumentParser(description="Compile and run a CLE program")
	parser.add_argument("source", type=Path, help="path to a .cle file")
	args = parser.parse_args(argv)
	try:
		run_file(args.source)
	except (CLECompileError, RuntimeError, SyntaxError) as error:
		print(error, file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
