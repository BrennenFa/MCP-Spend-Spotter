import concurrent.futures
from sentence_transformers import SentenceTransformer, CrossEncoder


# CI/CD file
# download models in parrallel for speed
# yes im aware its small
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    executor.submit(SentenceTransformer, 'all-MiniLM-L6-v2')
    executor.submit(CrossEncoder, 'cross-encoder/ms-marco-MiniLM-L-6-v2')

