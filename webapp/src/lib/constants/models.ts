import type { Language } from "../../types/workbench";

export const modelGroups = [
  {
    provider: "Google",
    models: [
      { value: "gemini/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { value: "gemini/gemini-2.5-pro", label: "Gemini 2.5 Pro" },
    ],
  },
  {
    provider: "OpenAI",
    models: [{ value: "gpt-4o-mini", label: "GPT-4o mini" }],
  },
  {
    provider: "Anthropic",
    models: [{ value: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku" }],
  },
  {
    provider: "DeepSeek",
    models: [
      { value: "deepseek/deepseek-v4-pro", label: "DeepSeek V4 Pro" },
      { value: "deepseek/deepseek-v4-flash", label: "DeepSeek V4 Flash" },
      { value: "deepseek/deepseek-chat", label: "DeepSeek Chat" },
      { value: "deepseek/deepseek-reasoner", label: "DeepSeek Reasoner" },
    ],
  },
  {
    provider: "Qwen / DashScope",
    models: [
      { value: "dashscope/qwen-plus", label: "Qwen Plus" },
      { value: "dashscope/qwen-max", label: "Qwen Max" },
      { value: "dashscope/qwen-turbo", label: "Qwen Turbo" },
      { value: "dashscope/qwen3-235b-a22b", label: "Qwen3 235B A22B" },
      { value: "dashscope/qwen3-32b", label: "Qwen3 32B" },
    ],
  },
  {
    provider: "MiMo / Xiaomi",
    models: [
      { value: "openai/mimo-v2.5-pro", label: "MiMo v2.5 Pro" },
      { value: "openai/mimo-v2.5", label: "MiMo v2.5" },
      { value: "openai/mimo-v2-pro", label: "MiMo v2 Pro" },
      { value: "openai/mimo-v2-flash", label: "MiMo v2 Flash" },
    ],
  },
];

export const deepseekProModelName = "deepseek/deepseek-v4-pro";
export const deepseekReasonerModelName = "deepseek/deepseek-reasoner";
export const mimoProModelName = "openai/mimo-v2.5-pro";
export const defaultLanguage: Language = "zh";
export const defaultModelName = deepseekProModelName;
export const workflowPhaseCount = 7;
