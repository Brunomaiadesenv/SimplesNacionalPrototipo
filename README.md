# Fiscalização do Simples Nacional — protótipo (ISS Digital)

Protótipo em **Python + FastAPI** da rotina de fiscalização do Simples Nacional: confronta o que o contribuinte **declarou**
no PGDAS-D com o que foi **escriturado** no ISSWEB (`Bia`) e com o que foi **pago** (`Parcelas`), classifica as diferenças
em D00–D08, permite tratar cada divergência e faz a baixa do pagamento.

Segue a estrutura e a forma de comunicação do protótipo `auditoria_api` (mesmo desenho de pastas, `.env`, travas de proteção,
log de uso, modo demonstração, `verificar-colunas`, `run.bat`) e implementa a arquitetura do *Guia do programador*.
Roda **de ponta a ponta no modo demonstração**, sem SQL Server, com dados fictícios.

## Como rodar (Windows)

1. Instale o Python 3.11+ (marque *Add python.exe to PATH*). Funciona offline com Python 3.11, 3.12 ou 3.13 de 64 bits.
2. Dê duplo clique em `run.bat` (cria o ambiente, instala as dependências da pasta `pacotes`, cria o `.env` e o `demo.db` na primeira vez).
3. Abra http://127.0.0.1:8000 — a documentação interativa da API está em `/docs`.

Linux/macOS: `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python criar_demo.py && .venv/bin/python -m uvicorn app.main:app`

Teste de aceite: `python testar.py` (68 cenários, usa banco temporário).

## Roteiro de demonstração (PA 202510)

1. **Simular confronto** → 52 declarações, 20 divergências (somente leitura; nada é gravado).
2. **Executar e gravar** → cria a execução; agora cada divergência pode ser tratada (Pendente / Justificada / Notificada).
3. Clique numa divergência → **Análise do contribuinte** com as três grades: DAS (`PGDASD01000`), escrituração (`Bia`) e rateio (`PGDASD01100`).
4. **Baixa** → *Simular baixa* mostra o que será gravado em `Parcelas.VrAutenticadoSuperSimples`; *Baixar* grava; *Estornar* devolve o valor anterior.
5. **Carga do arquivo** → envie `exemplos/pgdasd_exemplo.txt` (layout hipotético): importa 6 declarações, registra 1 linha inválida e recusa o mesmo arquivo na segunda vez (hash). A PA 202511 passa a existir (todos os CNPJs do exemplo caem em D01, pois não estão no cadastro de demonstração).

### Instalação sem internet
A pasta `pacotes/` já traz as dependências para Windows 64 bits (Python 3.11, 3.12 e 3.13); o `run.bat` as usa sozinho (o pip escolhe o pacote da sua versão) e não precisa de internet.
Se a sua versão do Python for outra, em um computador com internet rode `pip download -r requirements.txt -d pacotes\cp3XX` (XX = versão) ou, com proxy, `pip install --proxy http://usuario:senha@proxy:porta -r requirements.txt`.
Para usar o SQL Server instale também `requirements-sqlserver.txt` (inclui o `pyodbc`).

## Divergências

| Cód. | O que é | Regra |
|---|---|---|
| D00 | Carga inconsistente | Σ `PGDASD03110.ValorApuradoISS` ≠ `PGDASD02000.ISS`; a declaração fica fora do confronto e da baixa |
| D01 | CNPJ declarado sem cadastro | CNPJ de `PGDASD03000` não existe em `Contribu` |
| D02 | Declarou, não escriturou como Simples | receita no município e nenhuma linha de Simples em `Bia` |
| D03 | Escriturou como Simples, sem declaração | `Bia` (PT='P', SuperSimples='S') sem declaração vigente |
| D04 | Receita diferente | \|Σ `03110.Valor` − Σ `Bia.VrBruto`\| > tolerância |
| D05 | ISS diferente | \|Σ `03110.ValorApuradoISS` − Σ `Bia.VrImposto`\| > tolerância |
| D06 | Alíquota diferente | alíquotas ponderadas diferem mais de 0,01 p.p. |
| D07 | Pagamento diferente | Σ `01100.valorprinc` do município ≠ `Parcelas.VrAutenticadoSuperSimples` **já baixado** |
| D08 | Optante sem adesão vigente | PA fora de `DtAdesao`–`DtCancelamento`; sem histórico em `SuperSimples` segue o flag (regra de transição) |

Tolerância: R$ 0,05 por contribuinte e PA (`TOLERANCIA_ABS`), congelada em cada execução. A declaração **vigente** é a de maior
`Pgdasd_Dt_Transmissao` por `Cnpjmatriz`+`Pa` (view `vw_PgdasDeclaracaoVigente`), o que trata as retificadoras.

### Decisões do protótipo que divergem ou detalham o Guia (valide com a Fiscalização)

- **D02** só dispara se a receita declarada ao município for > 0 (evita ruído de declarações zeradas).
- **D07** só compara parcelas já baixadas. Valor ainda vazio não é divergência: aparece na *Baixa* como "gravar".
- **Baixa**: por padrão só preenche onde está vazio; valor diferente já existente aparece como "sobrescrever" e só é trocado com confirmação explícita. Parcela inexistente ou ambígua (mais de uma) não é adivinhada. Declaração com D00 não é baixada.
- **Estorno**: a tabela nova `ConfrontoBaixa` guarda o valor anterior e o estorno o restaura (o Guia dizia "zerar").
- O cruzamento FULL JOIN por CNPJ é feito em Python sobre agregações SQL (mesmo resultado em SQL Server e SQLite, e testável).

## Login, menu e novas rotinas (versão 2)

**Acesso de teste (banco de exemplo):** usuário `supervisor`, senha `167421es` (também existe `fiscal` / `fiscal123`, sem privilégio de supervisor).
No SL_ISS real, crie o usuário de teste com `sql/criar_usuario_supervisor.sql` e **troque a senha ou remova o usuário depois dos testes**.

- **Login:** compara com `dbo.Usuario` (`NomeUsuario` ou `CodigoUsuario`, sem diferenciar maiúsculas), exige `Ativo = 1` e a janela `DtInicio`–`DtExpiracao`. Bloqueia após 5 erros em 10 min (usuário + IP). Perfil supervisor = `Privilegio` em `PRIVILEGIOS_ADMIN` (padrão `S`, editável em Configuração).
- **Atenção:** `dbo.Usuario.Senha` é `varchar(10)` em texto puro; o sistema compara direto e nunca devolve nem registra a senha. Recomenda-se migrar para hash no ISS Digital.
- **Menu vertical:** Fiscalização (tela original), Contribuinte (`dbo.Contribu`), Usuário (`dbo.Usuario`, só supervisor), Configuração (só supervisor: credenciais do banco, cliente, período ativo AAAAMM, brasão, módulo e grupo de cálculo inteiros, prazos, SMTP). Salva em `data/config.json` (senhas nunca são exibidas; em branco = mantém).
- **Imprimir relatório:** botão ao lado de “Executar e gravar”; vale para simulação e execução gravada (A4 paisagem).
- **Ações por divergência (exigem execução gravada):**

| Código | Ação |
|---|---|
| D00 | Somente alerta. Nada é executado. |
| D01 | **Cadastrar como Eventual**: grava razão social + CNPJ em `dbo.Contribu` com código de prefixo **5** e marca “Regularizada”. |
| D02, D03, D06, D07, D08 | **Notificar**: método `acoes.enviar_notificacao` abre a notificação já preenchida com os dados do confronto (editável), registra em `SimplesNotificacao`, envia por e-mail se houver SMTP e e-mail do contribuinte, e marca “Notificada”. Ponto de extensão para o canal DTE. |
| D04, D05 | **Gerar cálculo**: grava `Calc1` (módulo/grupo da Configuração), `Parcelam` (parcela 01) e `Parcelas` (controle de emissão, `QtdEmitido = 0`), uma vez por contribuinte e competência. Valor: diferença de ISS (D05) ou receita não escriturada × alíquota declarada (só D04). Marca “Cálculo lançado”. |

### Pendências para o banco real (leia antes de habilitar escrita)
1. Não recebi as colunas de `Contribu`, `Calc1`, `Parcelam` e `Parcelas`. Os nomes em `app/mapeamento.py` são **hipóteses** marcadas `[PENDENTE]`. Rode `sql/colunas_obrigatorias.sql`, ajuste os nomes e preencha `*_PADRAO` com as colunas `NOT NULL` sem default.
2. Interpretei “dbo.Cac1” como **dbo.Calc1**. Se for outra tabela, ajuste `CALC1` no mapeamento.
3. A geração de cálculo vem **desligada** no banco real: só habilite em Configuração depois de testar em base de homologação.
4. Crie `ConfrontoAcao` e `SimplesNotificacao` com `sql/ddl_confronto.sql`.
5. O cálculo grava `Parcelas.NumeroParcelamento`; a baixa do Simples ignora essas linhas (`NumeroParcelamento IS NULL`). Confirme que esse é o elo real entre Parcelas e Parcelam.
6. Domínio dos flags `'S'/'N'` e do `Privilegio` em `dbo.Usuario` é hipótese.

## Travas de proteção (mesmo espírito do auditoria_api)

- Consultas **parametrizadas**, `WITH (NOLOCK)`, `LOCK_TIMEOUT`, `DEADLOCK_PRIORITY LOW`, `READ UNCOMMITTED`, timeout por consulta.
- Máximo de consultas simultâneas (`MAX_SIMULTANEAS`) → HTTP 429; timeout → 504; paginação com limite.
- **Escrita desligada por padrão no SQL Server** (`ESCRITA_PERMITIDA=false`): simulação, análise e consultas funcionam com login só de leitura; gravar exige login separado (`SQLSERVER_CONN_ESCRITA`) restrito às tabelas do módulo e à **única** coluna do legado que o confronto grava (`Parcelas.VrAutenticadoSuperSimples`).
- Login pela tabela `dbo.Usuario`, sessão em cookie assinado e **log de uso** (`uso.db`).
- Nada é gravado em `Bia`, `Calc1` ou `Contribu`.

## Passando para o banco real (SL_ISS)

1. Rode `sql/descobrir_colunas.sql` e confira os campos marcados **[PENDENTE]** em `app/colunas.py` (CNPJ em `Contribu`, formato de `Bia.AnoMes`, elo `Parcelas`→`Calc1`→`Bia`, colunas de `SuperSimples`).
2. Revise e rode `sql/ddl_confronto.sql` (4 tabelas novas, colunas `Hash`/`NumeroLinha`, a view de vigência e os índices — `Bia` tem 11,8 milhões de linhas, crie índices fora do horário de pico).
3. Rode `sql/preparar_banco.sql` (logins de leitura e de escrita).
4. No `.env`: `DB_MODE=sqlserver`, `SQLSERVER_CONN`, `COD_TOM` (veja `dbo.tabela_tom`) e `COD_MUNIC_01100`.
5. Abra `/api/verificar-colunas`: deve responder `tabelas_com_problema: 0`.
6. Comece **só simulando** e compare com uma PA conferida à mão antes de liberar a escrita.

## O que ainda não está validado (limites do protótipo)

- **Nunca rodou contra o SQL Server real**: o caminho `sqlserver` (T-SQL, `OUTPUT INSERTED`, `OFFSET/FETCH`) foi escrito mas só o modo demo (SQLite) foi executado. Valide em homologação.
- **Layout do arquivo PGDAS-D é hipotético** (`app/carga.py`, `exemplos/pgdasd_exemplo.txt`): falta um arquivo real e o manual do layout. Hierarquia 03000→03100→03110 e subníveis 03111–03132 não foram tratados.
- Parcelas por competência assumem `Parcelas.AnoMes`; o elo real (`Parcelas`→`Calc1`→`Bia`) é pendência. A coluna de CNPJ em `Contribu` é suposição (`Cnpj`).
- `PGDASD01100.codmunic` pode ser TOM ou IBGE (`COD_MUNIC_01100`).
- Unidade das alíquotas (% ou fração) e a tolerância oficial precisam de confirmação da Fiscalização.
- Fora do escopo desta versão: MEI (`PGMEI*`, `PERMEI_*`), DEFIS, PGFN, compensação, perfis de usuário e a integração com o fluxo de notificação/auto de infração do DTE.

## Estrutura

```
app/main.py        rotas, autenticação, travas, log de uso      app/confronto.py  regras D00–D08, baixa e estorno
app/queries.py     SQL parametrizado (SQL Server/SQLite)        app/carga.py      leitura e importação do arquivo
app/db.py          conexão, semáforo, transações, paginação      app/colunas.py    mapeamento de colunas + códigos (AJUSTAR)
app/config.py      leitura do .env                              app/static/       login.html + index.html (HTML + JS puro)
app/auth.py        login/sessão (dbo.Usuario)                   app/settings.py   Configuração (data/config.json)
app/cadastros.py   Contribuinte e Usuário                       app/acoes.py      ações D01 / notificação / cálculo
app/mapeamento.py  colunas de Usuario/Contribu/Calc1/... (AJUSTAR)
criar_demo.py      dados fictícios (gabarito em exemplos/)      testar.py         68 testes de aceite
sql/               DDL, logins, descoberta de colunas           exemplos/         arquivo de carga de exemplo
```
