from openai import OpenAI
import os, dotenv

dotenv.load_dotenv(".env")
print(os.getenv("C_OPENAI_KEY"))