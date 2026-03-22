# =============================================================
#  config.py — Configurações do Repositório TRF2 Previdenciário
# =============================================================
#
#  ⚠️  PASSO 1: Obtenha sua API Key gratuita em:
#      https://datajud-wiki.cnj.jus.br/api-publica/acesso
#
#  ⚠️  PASSO 2: Cole a chave abaixo substituindo "SUA_CHAVE_AQUI"
#
# =============================================================

# Chave de autenticação da API Pública DataJud / CNJ
# Obtenha em: https://datajud-wiki.cnj.jus.br/api-publica/acesso
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

# Caminho do banco de dados SQLite (será criado automaticamente)
DB_PATH = "jurisprudencia_trf2.db"

# Quantos dias retroativos buscar a cada execução
# 7 = última semana (recomendado para agendamento semanal)
# Na primeira execução, aumente para 365 para popular o histórico
DIAS_RETROATIVOS = 365
