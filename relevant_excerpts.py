import json
import numpy as np
import os
import tiktoken
from log_config import logger

def get_cache_fname(pdf_path, path_fxn):
    try:
        pdf_fname = os.path.basename(pdf_path)
        cache_dir = path_fxn("embeddings_cache")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        return f"{cache_dir}/{pdf_fname.replace('.pdf','.json')}"
    except Exception as e:
        logger.exception(f"Failed to construct internal filename {pdf_path}: {e}")
        raise

def cache_embeddings(embeddings, text_chunks, pdf_file_path, path_fxn):
    json_file_path = get_cache_fname(pdf_file_path, path_fxn)
    output_dict = {"embeddings": embeddings, "text_chunks": text_chunks}
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(output_dict, f)


def generate_embeddings(openai_client, text, model="text-embedding-3-small"):
    try:
        response = openai_client.embeddings.create(model=model, input=text)
        return response
    except Exception as e:
        logger.info(f"Failed to generate embeddings for the following text: {text}")
        logger.exception(f"While trying to construct embeddings for a provided text, the following error ocurred: {e}")
        raise

def generate_embedding(openai_client, text):
    try:
        r = generate_embeddings(openai_client, text)
        return r.data[0].embedding
    except Exception as e:
        logger.info(f"Failed to generate embeddings for the following text: {text}")
        logger.exception(f"While trying to construct embeddings for a provided text, the following error ocurred: {e}")
        raise

def generate_all_embeddings(openai_client, pdf_path, text_chunks, path_fxn):
    embeddings_model, token_limit = "text-embedding-3-small", 8000
    cache_fname = get_cache_fname(pdf_path, path_fxn)
    if os.path.exists(cache_fname):
        try:
            with open(cache_fname, "r", encoding="utf-8") as f:
                cached_embeddings = json.load(f)
                return cached_embeddings["embeddings"], cached_embeddings["text_chunks"]
        except Exception as e:
            logger.exception(f"While trying to cache embeddings for {cache_fname}, the following error ocurred: {e}")
            raise
    else:
        try:
            batches = []
            current_batch = []
            current_tokens = 0
            enc = tiktoken.encoding_for_model(embeddings_model)
            for text in text_chunks:
                tokens = len(enc.encode(text))
                if current_tokens + tokens > token_limit:
                    batches.append(current_batch)
                    current_batch = [text]
                    current_tokens = tokens
                else:
                    current_batch.append(text)
                    current_tokens += tokens
            if len(current_batch) > 0:
                batches.append(current_batch)

            embeddings = []
            for batch in batches:
                response = generate_embeddings(openai_client, batch, embeddings_model)
                embeddings.extend([r.embedding for r in response.data])

            cache_embeddings(embeddings, text_chunks, pdf_path, path_fxn)
            return embeddings, text_chunks
        except Exception as e:
            logger.exception(f"While trying to construct embeddings for a {pdf_path}, the following error ocurred: {e}")
            raise
def embed_one_variable_specification(openai_client, prompt):
    try:
        return generate_embedding(openai_client, prompt)
    except Exception as e:
        logger.info(f"Attemped to embed the following prompt: {prompt}")
        logger.exception(f"Received error: {e}")
        raise
def embed_variable_specifications(openai_client, variables):
    var_embeddings = {}
    try:
        for var in variables:
            prompt = var
            spec_dict = {"variable_description": "", "context": ""}
            if "variable_description" in variables[var]:
                var_desc = variables[var]["variable_description"]
                if len(var_desc) > 1:
                    prompt = f"{var}: '{var_desc}'"
                    spec_dict["variable_description"] = var_desc
            if "context" in variables[var]:
                context = variables[var]["context"]
                if len(context) > 1:
                    prompt += f". Context: {context}"
                    spec_dict["context"] = context
            spec_dict["embedding"] = embed_one_variable_specification(openai_client, prompt)
            var_embeddings[var] = spec_dict
        return var_embeddings
    except Exception as e:
        logger.info(f"Attemped to embed the following variables: {variables}")
        logger.exception(f"Received error: {e}")
        raise
def cosine_similarity(a, b):
    try:
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    except Exception as e:
        logger.info(f"Failed to calculate a cosine similarity with the following error: {e}")
        raise
def find_top_relevant_texts(
    text_embeddings, pdf_text_chunks, var_embedding, num_excerpts, var_name
):
    try:
        relevant_texts = []
        indeces = set()
        similarity_scores = []
        for i in range(len(text_embeddings)):
            if var_name in pdf_text_chunks[i]:
                indeces.add(i)
                relevant_texts.append((text_embeddings[i], pdf_text_chunks[i]))
            text_embedding = text_embeddings[i]
            similarity = cosine_similarity(var_embedding, text_embedding)
            similarity_scores.append((i, similarity))
        # Sort by similarity score in descending order and take the top_n items
        sorted_embeddings = sorted(similarity_scores, key=lambda x: x[1], reverse=True)[
            :num_excerpts
        ]
        ## RETURNS [(textembed, text), ..., 10x] for each variable
        return relevant_texts + [
            (text_embeddings[i], pdf_text_chunks[i])
            for i, _ in sorted_embeddings
            if i not in indeces
        ]
    except Exception as e:
        logger.info(f"Failed to calculate text relevancy due to the following error: {e}")
        raise