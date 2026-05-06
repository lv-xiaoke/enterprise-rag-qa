from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "HELP.md"
TEX_PATH = ROOT / "HELP_PROJECT_GUIDE.tex"


SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_tex(text: str) -> str:
    return "".join(SPECIALS.get(ch, ch) for ch in text)


def inline_markup(text: str) -> str:
    escaped = escape_tex(text)
    parts: list[str] = []
    in_code = False
    buf: list[str] = []
    for ch in escaped:
        if ch == "`":
            segment = "".join(buf)
            buf = []
            if in_code:
                parts.append(r"\texttt{" + segment + "}")
            else:
                parts.append(segment)
            in_code = not in_code
        else:
            buf.append(ch)
    parts.append("".join(buf))
    if in_code:
        return "".join(parts).replace(r"\texttt{", "")
    return "".join(parts)


def heading(level: int, title: str) -> str:
    title = inline_markup(title)
    if level == 1:
        return r"\section*{" + title + "}\n" + r"\addcontentsline{toc}{section}{" + title + "}"
    if level == 2:
        return r"\section{" + title + "}"
    if level == 3:
        return r"\subsection{" + title + "}"
    return r"\subsubsection{" + title + "}"


def convert_markdown(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_code = False
    in_itemize = False
    in_enumerate = False

    def close_lists() -> None:
        nonlocal in_itemize, in_enumerate
        if in_itemize:
            out.append(r"\end{itemize}")
            in_itemize = False
        if in_enumerate:
            out.append(r"\end{enumerate}")
            in_enumerate = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            if not in_code:
                out.append(r"\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\small]")
                in_code = True
            else:
                out.append(r"\end{Verbatim}")
                in_code = False
            continue

        if in_code:
            out.append(line)
            continue

        if not stripped:
            close_lists()
            out.append("")
            continue

        if stripped.startswith("#"):
            close_lists()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            out.append(heading(level, title))
            continue

        if stripped.startswith("- "):
            if in_enumerate:
                out.append(r"\end{enumerate}")
                in_enumerate = False
            if not in_itemize:
                out.append(r"\begin{itemize}")
                in_itemize = True
            out.append(r"\item " + inline_markup(stripped[2:].strip()))
            continue

        numbered = False
        for i in range(1, 30):
            prefix = f"{i}. "
            if stripped.startswith(prefix):
                numbered = True
                if in_itemize:
                    out.append(r"\end{itemize}")
                    in_itemize = False
                if not in_enumerate:
                    out.append(r"\begin{enumerate}")
                    in_enumerate = True
                out.append(r"\item " + inline_markup(stripped[len(prefix):].strip()))
                break
        if numbered:
            continue

        close_lists()
        if stripped.startswith("> "):
            out.append(r"\begin{quote}" + inline_markup(stripped[2:].strip()) + r"\end{quote}")
        else:
            out.append(inline_markup(stripped) + r"\par")

    close_lists()
    if in_code:
        out.append(r"\end{Verbatim}")
    return "\n".join(out)


def main() -> None:
    body = convert_markdown(MD_PATH.read_text(encoding="utf-8"))
    tex = rf"""\documentclass[UTF8,zihao=-4]{{ctexart}}
\usepackage[a4paper,margin=2.2cm]{{geometry}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{enumitem}}
\usepackage{{fancyvrb}}
\hypersetup{{colorlinks=true,linkcolor=blue,urlcolor=blue}}
\setlist{{nosep,leftmargin=2em}}
\setlength{{\parskip}}{{0.45em}}
\setlength{{\parindent}}{{0pt}}
\title{{LangChain ReAct Agent 项目完整帮助文档}}
\author{{基于当前项目 HELP.md 自动生成}}
\date{{2026-05-06}}
\begin{{document}}
\maketitle
\tableofcontents
\newpage
{body}
\end{{document}}
"""
    TEX_PATH.write_text(tex, encoding="utf-8")
    print(TEX_PATH)


if __name__ == "__main__":
    main()
