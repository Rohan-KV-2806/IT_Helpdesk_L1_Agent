
# Local AI Setup

1. Create project + venv
```
mkdir IT-Helpdesk-L1-Agent
cd IT-Helpdesk-L1-Agent

python -m venv .venv
.venv\Scripts\activate
```

2. Install llama.cpp Python
```
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```
verify if installed correctly
```
python -c "from llama_cpp import Llama; print('SUCCESS')"
```

3. Create model folder
```
mkdir LocalLLMs
```

4. Install Hugging Face CLI 
```
pip install -U "huggingface_hub[cli]"
```

5. Download the model
```
hf download bartowski/SmolLM2-135M-Instruct-GGUF --include "Your model name" --local-dir LocalLLMs
```
replace with your model of choice along with its extension for example "LocalLLMs/Qwen_Qwen3-0.6B-Q4_K_M.gguf"

6. Check folder
```
IT-Helpdesk-L1-Agent/
├── .venv/
└── LocalLLMs/
    └── LocalLLMs/Qwen_Qwen3-0.6B-Q4_K_M.gguf
```

7. Test the model
```
python test/test_model.py
```
