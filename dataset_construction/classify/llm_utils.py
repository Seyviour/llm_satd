from langchain_openai import ChatOpenAI
from langchain_core.prompts.chat import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from pydantic import BaseModel, Field
import asyncio

class SATDLLMResponse(BaseModel):
    is_context_llm: bool = Field(description="True if the context contains LLM-related code or API usage, otherwise False")
    is_comment_satd: bool = Field(description="True if the comment is a self-admitted technical debt (SATD), otherwise False")
    explanation: str = Field(description="Short explanation for the decision")

SATD_LLM_PROMPT = ChatPromptTemplate(
    messages=[
        ("system", "You are an expert code reviewer. Given a code comment and its context, determine if the context uses LLM APIs or libraries, and if the comment is a self-admitted technical debt (SATD) such as TODO, FIXME, HACK, BUG, or XXX, related to the implementation and functionality surrounding the use of the LLM"),
        ("human", "Comment: {comment}\nContext: {context}\n\nRespond with your analysis."),
    ],
    input_variables=["comment", "context"]
)

class SATDLLMClassifier:
    def __init__(self, model="gpt-4o", api_key=None, rqs=50):
        self.rate_limiter = InMemoryRateLimiter(requests_per_second=rqs, check_every_n_seconds=0.01, max_bucket_size=150)
        self._chat = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            temperature=0,
            rate_limiter=self.rate_limiter,
        ).with_structured_output(SATDLLMResponse)

    async def classify(self, comment: str, context: str) -> dict:
        messages = SATD_LLM_PROMPT.format_messages(comment=comment, context=context)
        response = await self._chat.ainvoke(messages)  # async call
        return response.dict()


if __name__ == "__main__":
    classifier = SATDLLMClassifier(api_key="your_api_key_here")
    result = asyncio.run(classifier.classify(comment="TODO: refactor this", context="def foo(): )..."))
    print(result)