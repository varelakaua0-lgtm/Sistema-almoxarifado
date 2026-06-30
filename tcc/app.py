import os
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import mysql.connector

app = Flask(__name__)
app.secret_key = "Senai"
app.config['IMG_FOLDER'] = 'static/img'
os.makedirs('static/img', exist_ok=True)


def banco():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="almoxarifado"
    )


@app.route('/')
def login():
    return render_template("index.html")


@app.route('/home')
def home():
    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT nome, quantidade, imagem FROM estoque ORDER BY id DESC")
    ultimos = cursor.fetchall()
    cursor.close()
    conexao.close()
    return render_template("home.html", ultimos=ultimos)


@app.route('/adicionaritens')
def adicionaritens():
    return render_template("adicionaritens.html")


@app.route('/estoque')
def estoque():
    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque")
    itens = cursor.fetchall()
    cursor.close()
    conexao.close()
    return render_template("estoque.html", itens=itens)


@app.route('/saidas')
def saidas():
    if session.get('tipo') != 'adm':
        return """<script>alert("Acesso restrito ao administrador!"); window.location.href = "/home";</script>"""
    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque")
    itens = cursor.fetchall()
    cursor.execute("SELECT * FROM log_deletes ORDER BY id DESC")
    log = cursor.fetchall()
    cursor.close()
    conexao.close()
    return render_template("saidas.html", itens=itens, log=log)


@app.route('/criarconta')
def criarconta():
    return render_template("criarconta.html")


# ========== LOGIN ==========
@app.route('/api/login', methods=['POST'])
def apilogin():
    username = request.form['username']
    senha = request.form['senha']

    if username.lower() == 'admin12' and senha == 'admin1212':
        session['usuario'] = username
        session['tipo'] = 'adm'
        return redirect(url_for('home'))

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuario WHERE usuario = %s AND senha = %s", (username, senha))
    usuario = cursor.fetchone()
    cursor.close()
    conexao.close()

    if usuario:
        session['usuario'] = username
        session['tipo'] = 'user'
        return redirect(url_for('home'))

    return """<script>alert("Usuário ou senha incorretos"); window.location.href = "/";</script>"""


# ========== CRIAR CONTA ==========
@app.route('/api/criarconta', methods=['POST'])
def api_criarconta():
    username = request.form['username']
    senha = request.form['senha']
    confirmar = request.form['confirmar']

    if senha != confirmar:
        return """<script>alert("As senhas não coincidem"); window.location.href = "/criarconta";</script>"""

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT id FROM usuario WHERE usuario = %s", (username,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        conexao.close()
        return """<script>alert("Usuário já cadastrado!"); window.location.href = "/criarconta";</script>"""

    cursor2 = conexao.cursor()
    cursor2.execute("INSERT INTO usuario (usuario, senha) VALUES (%s, %s)", (username, senha))
    conexao.commit()
    cursor2.close()
    cursor.close()
    conexao.close()

    return """<script>alert("Conta criada com sucesso!"); window.location.href = "/";</script>"""


# ========== ADICIONAR ITEM ==========
@app.route('/api/adicionaritem', methods=['POST'])
def adicionaritem():
    nome = request.form['nome']
    categoria = request.form['categoria']
    descricao = request.form['descricao']
    preco = request.form['preco']
    quantidade = request.form['quantidade']
    estoqueminimo = request.form['estoqueminimo']

    imagem = request.files.get('imagem')
    caminho_imagem = None
    if imagem and imagem.filename != '':
        caminho_imagem = imagem.filename
        imagem.save(os.path.join(app.config['IMG_FOLDER'], imagem.filename))

    conexao = banco()
    cursor = conexao.cursor()
    cursor.execute(
        "INSERT INTO estoque (nome, categoria, descricao, preco, quantidade, estoque_min, imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (nome, categoria, descricao, preco, quantidade, estoqueminimo, caminho_imagem)
    )
    conexao.commit()
    cursor.close()
    conexao.close()

    return """<script>alert("Item adicionado com sucesso!"); window.location.href = "/estoque";</script>"""


# ========== DELETAR ITEM DO ESTOQUE ==========
@app.route("/api/deletaritem/<int:id>", methods=["DELETE"])
def api_deletaritem(id):
    if session.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso negado."})

    dados = request.get_json()
    nome_admin  = dados.get('nome_admin', 'admin') if dados else 'admin'
    data_delete = dados.get('data_delete') if dados else None

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque WHERE id = %s", (id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        conexao.close()
        return jsonify({"ok": False, "erro": "Item não encontrado"})

    cursor2 = conexao.cursor()
    # Salva no log_deletes
    cursor2.execute(
        "INSERT INTO log_deletes (nome_admin, item, categoria, descricao, preco, qtde, estoque_min, data_delete) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (nome_admin, item['nome'], item['categoria'], item['descricao'], item['preco'], item['quantidade'], item['estoque_min'], data_delete)
    )
    # Também salva na tabela saidas (mantém compatibilidade)
    cursor2.execute(
        "INSERT INTO saidas (item, qtde, descricao, preco, categoria, estoque_min) VALUES (%s, %s, %s, %s, %s, %s)",
        (item['nome'], item['quantidade'], item['descricao'], item['preco'], item['categoria'], item['estoque_min'])
    )
    cursor2.execute("DELETE FROM estoque WHERE id = %s", (id,))
    conexao.commit()
    cursor2.close()
    cursor.close()
    conexao.close()
    return jsonify({"ok": True, "mensagem": f"Item '{item['nome']}' deletado com sucesso!"})


# ========== BUSCAR ITEM POR ID ==========
@app.route('/api/item/<int:id>')
def api_item(id):
    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT nome FROM estoque WHERE id = %s", (id,))
    item = cursor.fetchone()
    cursor.close()
    conexao.close()
    return jsonify(item if item else {})



# ========== EXPORTAR CSV ==========
@app.route("/exportar-csv")
def exportar_csv():
    if session.get('tipo') != 'adm':
        return jsonify({"erro": "Acesso negado."})

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["## ESTOQUE"])
    writer.writerow(["id", "nome", "categoria", "descricao", "preco", "quantidade", "estoque_min", "imagem"])
    cursor.execute("SELECT id, nome, categoria, descricao, preco, quantidade, estoque_min, imagem FROM estoque")
    for row in cursor.fetchall():
        writer.writerow(row.values())

    writer.writerow([])

    writer.writerow(["## SAIDAS"])
    writer.writerow(["id", "item", "categoria", "descricao", "preco", "qtde", "estoque_min"])
    cursor.execute("SELECT id, item, categoria, descricao, preco, qtde, estoque_min FROM saidas")
    for row in cursor.fetchall():
        writer.writerow(row.values())

    writer.writerow([])

    writer.writerow(["## USUARIOS"])
    writer.writerow(["id", "nome", "email"])
    cursor.execute("SELECT id, nome, email FROM usuario")
    for row in cursor.fetchall():
        writer.writerow(row.values())

    cursor.close()
    conexao.close()

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="backup_almoxarifado.csv"
    )


# ========== IMPORTAR CSV ==========
@app.route("/importar-csv", methods=["POST"])
def importar_csv():
    if session.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso negado."})

    arquivo = request.files.get("arquivo")
    if not arquivo:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."})

    conteudo = arquivo.read().decode("utf-8")
    reader = csv.reader(io.StringIO(conteudo))

    conexao = banco()
    cursor = conexao.cursor()

    secao = None
    cabecalho = False
    importados = {"estoque": 0, "saidas": 0, "usuarios": 0}

    for linha in reader:
        if not linha or all(c == "" for c in linha):
            cabecalho = False
            continue
        if linha[0] == "## ESTOQUE":
            secao = "estoque"; cabecalho = True; continue
        if linha[0] == "## SAIDAS":
            secao = "saidas"; cabecalho = True; continue
        if linha[0] == "## USUARIOS":
            secao = "usuarios"; cabecalho = True; continue
        if cabecalho:
            cabecalho = False; continue

        if secao == "estoque":
            cursor.execute(
                "INSERT INTO estoque (nome, categoria, descricao, preco, quantidade, estoque_min, imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (linha[1], linha[2], linha[3], linha[4], linha[5], linha[6], linha[7] if len(linha) > 7 else None)
            )
            importados["estoque"] += 1
        elif secao == "saidas":
            cursor.execute(
                "INSERT INTO saidas (item, categoria, descricao, preco, qtde, estoque_min) VALUES (%s, %s, %s, %s, %s, %s)",
                (linha[1], linha[2], linha[3], linha[4], linha[5], linha[6])
            )
            importados["saidas"] += 1
        elif secao == "usuarios":
            cursor.execute(
                "INSERT INTO usuario (nome, email) VALUES (%s, %s)",
                (linha[1], linha[2])
            )
            importados["usuarios"] += 1

    conexao.commit()
    cursor.close()
    conexao.close()

    return jsonify({"ok": True, "importados": importados})


# ========== APAGAR TODO O BANCO ==========
@app.route("/api/apagar-banco", methods=["DELETE"])
def apagar_banco():
    if session.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso negado."})
    conexao = banco()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM estoque")
    cursor.execute("DELETE FROM saidas")
    cursor.execute("DELETE FROM log_deletes")
    cursor.execute("DELETE FROM usuario")
    conexao.commit()
    cursor.close()
    conexao.close()
    return jsonify({"ok": True})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')