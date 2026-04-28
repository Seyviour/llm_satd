import re
from pathlib import Path

exclude = ["append", "get", "join", "update", "info", "copy", "load", "items", "split", 
            "extend", "run", "replace", "pop", "zeros", "strip", "close", "format", 
            "startswith", "keys", "call", "remove", "debug", "delete"]

def build_optional_prefix_regex(line: str):
    line = line or ''
    parts = line.strip().split(".")
    if not parts: return None
    if len(parts) < 2:
        if parts[0] in exclude:
            return None
        if parts[0][0].isupper():
            return rf"\b{re.escape(parts[0])}\s*\("
        return rf"\.{re.escape(parts[0])}\s*\("

    *prefixes, final = parts
    regex = ""
    for p in prefixes:
        regex += rf"(?:{re.escape(p)}\.)?"

    if final in exclude or not prefixes[-1][0].isupper():
        regex = regex[:-1]  # makes last prefix mandatory

    if final[0].isupper():
        regex += rf"\b{re.escape(final)}\s*\("
    else:
        regex += rf"{re.escape(final)}\s*\("   # <-- removed leading dot
    return regex


#path of this file
BASE_PATH = Path(__file__).parent

PATTERNS = {
    "openai": [
            re.compile(pattern)
            for line in Path(BASE_PATH / "extracted_apis/openai.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line.strip()))
        ],
    "anthropic": [
            re.compile(build_optional_prefix_regex(line))
            for line in Path(BASE_PATH / "extracted_apis/anthropic.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line))
        ],
    "mistralai": [
            re.compile(build_optional_prefix_regex(line))
            for line in Path(BASE_PATH / "extracted_apis/mistral.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line))
        ],
    "ollama": [
            re.compile(build_optional_prefix_regex(line))
            for line in Path(BASE_PATH / "extracted_apis/ollama.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line))
        ],
    "google-genai": [
            re.compile(build_optional_prefix_regex(line))
            for line in Path(BASE_PATH / "extracted_apis/google-genai.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line))
        ],
    "cohere": 
        [
            re.compile(build_optional_prefix_regex(line))
            for line in Path(BASE_PATH / "extracted_apis/cohere.txt").read_text().splitlines()
            if (pattern:=build_optional_prefix_regex(line))
        ],
    "langchain": [
        # Core and community/experimental Imports
        re.compile(r"\bimport\s+langchain(_core|_community|_experimental|_anthropic|_openai|_mistralai|_google_genai|_cohere|_ollama)?\b"),
        re.compile(r"\bfrom\s+langchain(_core|_community|_experimental|_anthropic|_openai|_mistralai|_google_genai|_cohere|_ollama)?\s+import\b"),
        # Common Class Instantiations (LangChain specific)
        re.compile(r"\b(LLMChain|SequentialChain|ConversationChain|APIChain|GraphQAChain|RetrievalQA(?:WithSources)?)\s*\("),
        re.compile(r"\b(Message|AIMessage|HumanMessage|ChatPromptTemplate|PromptTemplate|FewShotPromptTemplate|StringPromptTemplate|AIMessagePromptTemplate|HumanMessagePromptTemplate|SystemMessagePromptTemplate)\s*\("),
        re.compile(r"\b(ChatOpenAI|ChatAnthropic|ChatMistralAI|ChatGoogleGenerativeAI|ChatOllama|Ollama|ChatCohere)\s*\("),
        # Method Calls
        re.compile(r"\.\s*(invoke|ainvoke|batch|abatch|stream|astream|astream_log|transform_documents|embed_documents|embed_query)\s*\("),
        re.compile(r"\.\s*(run|arun|predict|apredict|call|acall|apply|map|aplan|plan|save|load|with_fallbacks|with_retry|with_config)\s*\("),
        re.compile(r"\|\s*(?:Runnable|ChatPromptTemplate|PromptTemplate|StrOutputParser|BaseOutputParser|LLMChain|BaseRetriever|OutputParser)"),
        re.compile(r"load_prompt\s*\("),
    ],
    "generic_mentions": [
        re.compile(r"openai|anthropic|mistralai|ollama|google-genai|cohere|langchain|llama|gemini|gpt|claude|lechat|mistral|llm", flags=re.IGNORECASE), #providers/libraries
    ]
}


def identify_llm_api_usage(code_content: str) -> list:
    """
    Identifies lines of code that use APIs of specified LLM packages in Python.
    """
    results = []
    code_content = code_content or ''
    code_content = str(code_content)

    lines = code_content.splitlines()
    # To avoid adding the same line multiple times for the same package
    detected_lines_for_package = set()

    for i, line_content in enumerate(lines):
        line_number = i + 1
        # Strip leading/trailing whitespace and also remove inline comments for more robust matching
        stripped_line = line_content.split('#', 1)[0].strip()
        # Skip empty lines (after comment removal)
        if not stripped_line:
            continue

        for package_name, patterns_list in PATTERNS.items():
            for pattern in patterns_list:
                if pattern.search(stripped_line):
                    if (line_number, package_name) not in detected_lines_for_package:
                        results.append((line_number, package_name, line_content))
                        detected_lines_for_package.add((line_number, package_name))
                    break
    return results

