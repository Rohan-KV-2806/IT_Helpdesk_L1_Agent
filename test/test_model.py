from llama_cpp import Llama

llm = Llama(
    model_path="models/SmolLM2-135M-Instruct-Q4_K_M.gguf",
    n_ctx=1024,
    n_threads=2,
    verbose=False
)

response = llm.create_chat_completion(
    messages=[
        {
            "role": "user",
            "content": "fuck you"
        }
    ],
    max_tokens=100
)

print(response["choices"][0]["message"]["content"])