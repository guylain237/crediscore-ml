# Image de l'API de scoring CrediScore.
#
# Elle contient le CODE, pas le modele. Le modele est un artefact versionne
# par MLflow : le figer dans l'image obligerait a reconstruire et redeployer
# a chaque reentrainement, et surtout on ne saurait plus, devant une
# contestation, quel modele exact a servi.
#
# En production, l'API telecharge le modele depuis le registre MLflow au
# demarrage. Sur le demonstrateur, il est monte en volume (voir le service
# api de docker/docker-compose.yml du depot mlops).
#
# Construction :  docker build -t crediscore-api:1.0 .
# Essai local  :  docker run -p 8000:8000 -v "$PWD/models:/app/models:ro" crediscore-api:1.0

FROM python:3.11-slim

# Les dependances d'abord, le code ensuite : Docker garde la couche des
# dependances en cache tant que requirements-api.txt ne bouge pas. Sans cette
# separation, chaque correction d'une ligne de Python reinstallerait
# LightGBM et SHAP.
WORKDIR /app

# LightGBM a besoin de la bibliotheque OpenMP, absente des images slim.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api/ ./api/
COPY src/ ./src/
COPY configs/ ./configs/

# L'API ne tourne pas en root. Un service expose sur le reseau qui s'execute
# avec tous les droits transforme la moindre faille en compromission de la
# machine (politique P-8, moindre privilege).
RUN useradd --create-home --uid 10001 crediscore \
    && chown -R crediscore:crediscore /app
USER crediscore

EXPOSE 8000

# La sonde interroge la vraie route de sante : elle verifie que le modele est
# charge, pas seulement que le processus est vivant.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/sante || exit 1

CMD ["uvicorn", "api.main:application", "--host", "0.0.0.0", "--port", "8000"]
