"""
=============================================================
 consulta.py — Ferramenta de Consulta ao Repositório TRF2
=============================================================
 Como usar (exemplos):

   python consulta.py                          → resumo geral
   python consulta.py --assunto "invalidez"    → filtro por assunto
   python consulta.py --orgao "1ª Turma"       → filtro por turma/órgão
   python consulta.py --classe "Auxílio-Doença"
   python consulta.py --de 2024-01-01 --ate 2024-12-31
   python consulta.py --exportar resultado.csv
=============================================================
"""

import sqlite3
import argparse
import csv
import json
from config import DB_PATH


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ── Consultas ──────────────────────────────────────────────────
def resumo_geral():
    """Exibe estatísticas gerais do repositório."""
    con = conectar()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) as total FROM processos")
    total = cur.fetchone()["total"]

    cur.execute("""
        SELECT classe_nome, COUNT(*) as qtd
        FROM processos
        GROUP BY classe_nome
        ORDER BY qtd DESC
        LIMIT 10
    """)
    classes = cur.fetchall()

    cur.execute("""
        SELECT orgao_julgador, COUNT(*) as qtd
        FROM processos
        GROUP BY orgao_julgador
        ORDER BY qtd DESC
        LIMIT 10
    """)
    orgaos = cur.fetchall()

    cur.execute("SELECT MAX(data_coleta) FROM processos")
    ultima = cur.fetchone()[0]

    con.close()

    print("\n" + "=" * 60)
    print("  REPOSITÓRIO TRF2 — JURISPRUDÊNCIA PREVIDENCIÁRIA")
    print("=" * 60)
    print(f"  Total de processos:  {total:,}")
    print(f"  Última atualização:  {ultima or 'N/A'}")

    print("\n  📁 Por Classe Processual:")
    for r in classes:
        print(f"     {r['classe_nome']:<45} {r['qtd']:>5}")

    print("\n  ⚖️  Por Órgão Julgador:")
    for r in orgaos:
        print(f"     {r['orgao_julgador']:<45} {r['qtd']:>5}")
    print()


def buscar(assunto=None, orgao=None, classe=None, de=None, ate=None, limite=50):
    """Busca processos com filtros opcionais."""
    con = conectar()
    cur = con.cursor()

    sql    = "SELECT * FROM processos WHERE 1=1"
    params = []

    if assunto:
        sql += " AND (assunto_principal LIKE ? OR assuntos_json LIKE ?)"
        params += [f"%{assunto}%", f"%{assunto}%"]
    if orgao:
        sql += " AND orgao_julgador LIKE ?"
        params.append(f"%{orgao}%")
    if classe:
        sql += " AND classe_nome LIKE ?"
        params.append(f"%{classe}%")
    if de:
        sql += " AND data_ajuizamento >= ?"
        params.append(de)
    if ate:
        sql += " AND data_ajuizamento <= ?"
        params.append(ate)

    sql += f" ORDER BY data_ultima_mov DESC LIMIT {limite}"

    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return rows


def exibir_resultados(rows):
    if not rows:
        print("\n  ⚠️  Nenhum processo encontrado com os filtros informados.\n")
        return

    print(f"\n  📋 {len(rows)} processo(s) encontrado(s):\n")
    print(f"  {'Nº Processo':<25} {'Classe':<30} {'Órgão':<25} {'Data Ajuiz.'}")
    print("  " + "-" * 100)
    for r in rows:
        print(f"  {r['numero_processo']:<25} {r['classe_nome'][:29]:<30} "
              f"{r['orgao_julgador'][:24]:<25} {r['data_ajuizamento']}")
    print()


def exportar_csv(rows, arquivo):
    if not rows:
        print("  Nenhum dado para exportar.")
        return

    colunas = rows[0].keys()
    with open(arquivo, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=colunas)
        writer.writeheader()
        for r in rows:
            row_dict = dict(r)
            # Remove JSONs internos para leitura mais limpa no Excel
            row_dict.pop("assuntos_json", None)
            row_dict.pop("movimentos_json", None)
            writer.writerow(row_dict)
    print(f"  ✅ Exportado para: {arquivo} ({len(rows)} registros)\n")


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Consulta ao Repositório de Jurisprudência TRF2"
    )
    parser.add_argument("--assunto",  help="Filtra por assunto (ex: 'invalidez')")
    parser.add_argument("--orgao",    help="Filtra por órgão julgador (ex: '1ª Turma')")
    parser.add_argument("--classe",   help="Filtra por classe (ex: 'Auxílio-Doença')")
    parser.add_argument("--de",       help="Data início YYYY-MM-DD")
    parser.add_argument("--ate",      help="Data fim YYYY-MM-DD")
    parser.add_argument("--limite",   type=int, default=50, help="Máx. de resultados (padrão: 50)")
    parser.add_argument("--exportar", metavar="ARQUIVO.csv", help="Exporta resultado para CSV")

    args = parser.parse_args()

    tem_filtro = any([args.assunto, args.orgao, args.classe, args.de, args.ate])

    if not tem_filtro:
        resumo_geral()
    else:
        rows = buscar(
            assunto=args.assunto,
            orgao=args.orgao,
            classe=args.classe,
            de=args.de,
            ate=args.ate,
            limite=args.limite
        )
        exibir_resultados(rows)
        if args.exportar:
            exportar_csv(rows, args.exportar)
