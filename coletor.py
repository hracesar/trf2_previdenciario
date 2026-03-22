"""
=============================================================
COLETOR DE JURISPRUDÊNCIA TRF2 — MATÉRIA PREVIDENCIÁRIA
Fonte: API Pública DataJud / CNJ
=============================================================
Como usar:
  1. Instale as dependências:  pip install requests
  2. Configure sua API Key no arquivo config.py
  3. Execute:  python coletor.py
=============================================================
"""

import requests
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from config import API_KEY, DB_PATH, DIAS_RETROATIVOS

# ── Configuração de log ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("coleta.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────
ENDPOINT = "https://api-publica.datajud.cnj.jus.br/api_publica_trf2/_search"
HEADERS  = {
    "Authorization": f"APIKey {API_KEY}",
    "Content-Type": "application/json"
}

TERMOS_PREVIDENCIARIOS = [
    "previdenciário", "previdenciária", "INSS", "aposentadoria",
    "auxílio-doença", "auxílio por incapacidade", "pensão por morte",
    "benefício assistencial", "benefício de prestação continuada",
    "salário-maternidade", "salário-família", "auxílio-acidente",
    "auxílio-reclusão", "aposentadoria especial", "tempo de contribuição",
    "invalidez", "incapacidade permanente", "LOAS", "BPC",
]

# ── Banco de dados ───────────────────────────────────────────
def criar_banco():
    con = sqlite3.connect(DB_PATH, timeout=30)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS processos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_processo     TEXT UNIQUE NOT NULL,
            classe_codigo       INTEGER,
            classe_nome         TEXT,
            assunto_principal   TEXT,
            assuntos_json       TEXT,
            orgao_julgador      TEXT,
            tribunal            TEXT DEFAULT 'TRF2',
            grau                TEXT,
            data_ajuizamento    TEXT,
            data_ultima_mov     TEXT,
            ultima_movimentacao TEXT,
            movimentos_json     TEXT,
            data_coleta         TEXT,
            url_processo        TEXT
        );

        CREATE TABLE IF NOT EXISTS coletas_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data_inicio TEXT,
            data_fim    TEXT,
            total_novos INTEGER,
            status      TEXT,
            mensagem    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_classe   ON processos(classe_codigo);
        CREATE INDEX IF NOT EXISTS idx_orgao    ON processos(orgao_julgador);
        CREATE INDEX IF NOT EXISTS idx_data_mov ON processos(data_ultima_mov);
        CREATE INDEX IF NOT EXISTS idx_assunto  ON processos(assunto_principal);
    """)
    con.commit()
    con.close()
    log.info("Banco de dados pronto: %s", DB_PATH)


# ── Consulta à API ────────────────────────────────────────────
def montar_query(data_inicio: str, data_fim: str, search_after=None) -> dict:
    should_clauses = [
        {"match": {"assuntos.nome": {"query": termo, "operator": "and"}}}
        for termo in TERMOS_PREVIDENCIARIOS
    ]
    query = {
        "size": 100,
        "sort": [
            {"dataHoraUltimaAtualizacao": "asc"},
            {"numeroProcesso.keyword": "asc"}
        ],
        "query": {
            "bool": {
                "must": [
                    {"range": {
                        "dataHoraUltimaAtualizacao": {
                            "gte": f"{data_inicio}T00:00:00",
                            "lte": f"{data_fim}T23:59:59"
                        }
                    }}
                ],
                "should": should_clauses,
                "minimum_should_match": 1
            }
        }
    }
    if search_after:
        query["search_after"] = search_after
    return query


def buscar_pagina(payload: dict) -> dict | None:
    try:
        resp = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        log.error("Erro HTTP: %s — Resposta: %s", e, resp.text[:300])
    except requests.exceptions.RequestException as e:
        log.error("Erro de conexão: %s", e)
    return None


def coletar_periodo(data_inicio: str, data_fim: str) -> list[dict]:
    todos = []
    search_after = None
    pagina = 1

    while True:
        log.info("Buscando página %d (período %s → %s)...", pagina, data_inicio, data_fim)
        payload   = montar_query(data_inicio, data_fim, search_after)
        resultado = buscar_pagina(payload)

        if not resultado:
            break

        hits = resultado.get("hits", {}).get("hits", [])
        if not hits:
            break

        todos.extend(hits)
        total_api = resultado.get("hits", {}).get("total", {}).get("value", "?")
        log.info("  → %d registros recebidos (acumulado: %d / %s na API)",
                 len(hits), len(todos), total_api)

        search_after = hits[-1].get("sort")
        pagina += 1

        if len(hits) < 100:
            break

    return todos


# ── Persistência ──────────────────────────────────────────────
def extrair_nome_assunto(item) -> str:
    """
    Extrai o nome do assunto de forma segura, independente da estrutura.
    A API pode retornar:
      - {"nome": "Aposentadoria"}          → dicionário normal
      - [{"nome": "Aposentadoria"}, ...]   → lista de dicionários
      - "Aposentadoria"                    → string direta
    """
    if isinstance(item, dict):
        return item.get("nome", "")
    elif isinstance(item, list):
        # Lista aninhada: pega o primeiro elemento
        if item and isinstance(item[0], dict):
            return item[0].get("nome", "")
        elif item and isinstance(item[0], str):
            return item[0]
    elif isinstance(item, str):
        return item
    return ""


def extrair_campos(doc: dict) -> dict:
    src = doc.get("_source", {})

    # ── Assuntos (tolerante a estruturas variadas) ──
    assuntos_raw = src.get("assuntos", [])
    assunto_principal = ""
    assuntos_normalizado = []

    for item in assuntos_raw:
        nome = extrair_nome_assunto(item)
        if nome:
            assuntos_normalizado.append({"nome": nome})
            if not assunto_principal:
                assunto_principal = nome

    # ── Último movimento ──
    movimentos = src.get("movimentos", [])
    ultima_mov = ""
    if movimentos:
        try:
            mov_ord = sorted(movimentos, key=lambda m: m.get("dataHora", "") if isinstance(m, dict) else "", reverse=True)
            primeira = mov_ord[0]
            ultima_mov = primeira.get("nome", "") if isinstance(primeira, dict) else ""
        except Exception:
            pass

    # ── Data de ajuizamento (normaliza formato) ──
    data_ajuiz_raw = str(src.get("dataAjuizamento", "") or "")
    if len(data_ajuiz_raw) >= 8 and "-" not in data_ajuiz_raw:
        data_ajuiz = f"{data_ajuiz_raw[0:4]}-{data_ajuiz_raw[4:6]}-{data_ajuiz_raw[6:8]}"
    else:
        data_ajuiz = data_ajuiz_raw[:10]

    return {
        "numero_processo":     src.get("numeroProcesso", ""),
        "classe_codigo":       src.get("classe", {}).get("codigo") if isinstance(src.get("classe"), dict) else None,
        "classe_nome":         src.get("classe", {}).get("nome", "") if isinstance(src.get("classe"), dict) else "",
        "assunto_principal":   assunto_principal,
        "assuntos_json":       json.dumps(assuntos_normalizado, ensure_ascii=False),
        "orgao_julgador":      src.get("orgaoJulgador", {}).get("nome", "") if isinstance(src.get("orgaoJulgador"), dict) else "",
        "grau":                src.get("grau", ""),
        "data_ajuizamento":    data_ajuiz,
        "data_ultima_mov":     (src.get("dataHoraUltimaAtualizacao") or "")[:10],
        "ultima_movimentacao": ultima_mov,
        "movimentos_json":     json.dumps(movimentos[:10], ensure_ascii=False),
        "data_coleta":         datetime.now().strftime("%Y-%m-%d"),
        "url_processo":        f"https://jurisprudencia.trf2.jus.br/processo/{src.get('numeroProcesso', '')}"
    }


def salvar_processos(docs: list[dict]) -> int:
    """Salva em lotes de 500 para evitar travamento do banco."""
    if not docs:
        return 0

    novos_total = 0
    lote_size   = 500

    for i in range(0, len(docs), lote_size):
        lote = docs[i:i + lote_size]
        con  = sqlite3.connect(DB_PATH, timeout=30)
        cur  = con.cursor()

        for doc in lote:
            try:
                campos = extrair_campos(doc)
                cur.execute("""
                    INSERT OR IGNORE INTO processos
                    (numero_processo, classe_codigo, classe_nome, assunto_principal,
                     assuntos_json, orgao_julgador, tribunal, grau,
                     data_ajuizamento, data_ultima_mov, ultima_movimentacao,
                     movimentos_json, data_coleta, url_processo)
                    VALUES
                    (:numero_processo, :classe_codigo, :classe_nome, :assunto_principal,
                     :assuntos_json, :orgao_julgador, 'TRF2', :grau,
                     :data_ajuizamento, :data_ultima_mov, :ultima_movimentacao,
                     :movimentos_json, :data_coleta, :url_processo)
                """, campos)
                if cur.rowcount > 0:
                    novos_total += 1
            except Exception as e:
                numero = doc.get("_source", {}).get("numeroProcesso", "?")
                log.warning("Ignorado processo %s: %s", numero, e)

        con.commit()
        con.close()
        log.info("  💾 Lote %d/%d salvo (%d novos acumulados)",
                 min(i + lote_size, len(docs)), len(docs), novos_total)

    return novos_total


def registrar_log(data_inicio, data_fim, total_novos, status, mensagem=""):
    try:
        con = sqlite3.connect(DB_PATH, timeout=30)
        con.execute("""
            INSERT INTO coletas_log (data_inicio, data_fim, total_novos, status, mensagem)
            VALUES (?, ?, ?, ?, ?)
        """, (data_inicio, data_fim, total_novos, status, mensagem))
        con.commit()
        con.close()
    except Exception as e:
        log.warning("Não foi possível registrar log: %s", e)


# ── Execução principal ────────────────────────────────────────
def executar_coleta():
    log.info("=" * 60)
    log.info("INICIANDO COLETA — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    criar_banco()

    data_fim    = datetime.now()
    data_inicio = data_fim - timedelta(days=DIAS_RETROATIVOS)

    str_inicio = data_inicio.strftime("%Y-%m-%d")
    str_fim    = data_fim.strftime("%Y-%m-%d")

    try:
        docs  = coletar_periodo(str_inicio, str_fim)
        novos = salvar_processos(docs)
        registrar_log(str_inicio, str_fim, novos, "OK")
        log.info("✅ Coleta concluída. Novos registros inseridos: %d", novos)
    except Exception as e:
        registrar_log(str_inicio, str_fim, 0, "ERRO", str(e))
        log.error("❌ Erro na coleta: %s", e)
        raise


if __name__ == "__main__":
    executar_coleta()
