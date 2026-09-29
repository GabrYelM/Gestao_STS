import sqlite3

conn = sqlite3.connect('contratos/stspe.db')
c = conn.cursor()

# Check all rows for Hospital Dia Penha CBO 225250 in staging_at02
c.execute("""
    SELECT nome_profissional, cod_procedimento, nome_procedimento, quantidade
    FROM staging_at02
    WHERE cod_cbo_sus = '225250'
      AND (cod_cnes = '2751933' OR cod_cmes IN (SELECT cod_cmes FROM estabelecimentos WHERE id = 16))
      AND ano_mes = '202601'
    ORDER BY nome_profissional, quantidade DESC
""")
print("Linhas de 225250 no Hospital Dia Penha:")
for r in c.fetchall():
    print(r)
