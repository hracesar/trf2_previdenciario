"""
=============================================================
 diagnostico.py — Testa a conexão com a API DataJud/CNJ
=============================================================
 Execute ANTES do coletor para confirmar que tudo está ok:

   python diagnostico.py

 Ele vai mostrar exatamente o que a API está retornando.
=============================================================
"""

import requests
import json
from config import API_KEY, DB_PATH

ENDPOINT = "https://api-publica.datajud.cnj.jus.br/api_publica_trf2/_search"
HEADERS  = {
    "Authorization": f"APIKey {API_KEY}",
    "Content-Type": "application/json"
}

def separador(titulo):
    print(f"\n{'=' * 55}")
    print(f"  {titulo}")
    print('=' * 55)


# ── TESTE 1: Conexão básica (sem filtros) ─────────────────────
def teste_conexao():
    separador("TESTE 1 — Conexão básica com a API")
    payload = {"size": 1, "query": {"match_all": {}}}
    try:
        r = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=15)
        print(f"  Status HTTP: {r.status_code}")
        if r.status_code == 200:
            total = r.json().get("hits", {}).get("total", {}).get("value", 0)
            print(f"  ✅ Conexão OK! Total de processos no índice: {total:,}")
            return True
        elif r.status_code == 401:
            print("  ❌ API Key inválida ou expirada.")
            print("     → Acesse datajud-wiki.cnj.jus.br/api-publica/acesso")
            print("       e atualize a chave no config.py")
        else:
            print(f"  ❌ Erro inesperado: {r.text[:300]}")
    except requests.exceptions.ConnectionError:
        print("  ❌ Sem conexão com a internet ou API fora do ar.")
    except Exception as e:
        print(f"  ❌ Erro: {e}")
    return False


# ── TESTE 2: Filtro por classe previdenciária ─────────────────
def teste_classe_previdenciaria():
    separador("TESTE 2 — Filtro por classe previdenciária")
    # Testa apenas Auxílio-Doença (1232) e Invalidez (1251)
    payload = {
        "size": 3,
        "query": {
            "terms": {"classe.codigo": [1232, 1251, 7791, 1229]}
        }
    }
    r = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=15)
    total = r.json().get("hits", {}).get("total", {}).get("value", 0)
    hits  = r.json().get("hits", {}).get("hits", [])
    print(f"  Processos encontrados com classes previdenciárias: {total:,}")
    if hits:
        print("  ✅ Exemplos encontrados:")
        for h in hits:
            src = h["_source"]
            print(f"     • {src.get('numeroProcesso','')} | "
                  f"{src.get('classe',{}).get('nome','')} | "
                  f"Atualizado: {str(src.get('dataHoraUltimaAtualizacao',''))[:10]}")
    else:
        print("  ⚠️  Nenhum resultado — os códigos de classe podem estar diferentes.")
        print("     → Executando teste 3 para investigar...")


# ── TESTE 3: Descobre quais classes existem no índice ─────────
def teste_descobrir_classes():
    separador("TESTE 3 — Classes processuais disponíveis no TRF2")
    payload = {
        "size": 0,
        "aggs": {
            "classes": {
                "terms": {"field": "classe.codigo", "size": 30}
            }
        }
    }
    r = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=15)
    buckets = r.json().get("aggregations", {}).get("classes", {}).get("buckets", [])
    if buckets:
        print("  Códigos de classe mais frequentes no índice TRF2:")
        for b in buckets[:15]:
            print(f"     Código {b['key']:>6}  →  {b['doc_count']:>8,} processos")
    else:
        print("  ⚠️  Não foi possível obter as agregações.")


# ── TESTE 4: Verifica o campo de data ─────────────────────────
def teste_campo_data():
    separador("TESTE 4 — Verificando campos de data disponíveis")
    payload = {"size": 1, "query": {"match_all": {}}}
    r = requests.post(ENDPOINT, headers=HEADERS, json=payload, timeout=15)
    hits = r.json().get("hits", {}).get("hits", [])
    if hits:
        src = hits[0]["_source"]
        campos_data = {k: v for k, v in src.items() if "data" in k.lower() or "hora" in k.lower()}
        print("  Campos de data encontrados no documento:")
        for campo, valor in campos_data.items():
            print(f"     {campo:<40} = {str(valor)[:30]}")
    else:
        print("  ⚠️  Nenhum documento retornado para inspecionar.")


# ── RESUMO ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  DIAGNÓSTICO — REPOSITÓRIO TRF2 PREVIDENCIÁRIO")
    print("=" * 55)
    print(f"  API Key configurada: {API_KEY[:8]}{'*' * (len(API_KEY)-8) if len(API_KEY) > 8 else '(muito curta!)'}")
    print(f"  Banco de dados:      {DB_PATH}")

    ok = teste_conexao()
    if ok:
        teste_classe_previdenciaria()
        teste_descobrir_classes()
        teste_campo_data()

    print("\n" + "=" * 55)
    print("  Diagnóstico concluído.")
    print("=" * 55 + "\n")
