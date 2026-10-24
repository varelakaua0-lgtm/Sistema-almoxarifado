import os
import csv
import io
import jwt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_bcrypt import Bcrypt
import mysql.connector

load_dotenv()
app = Flask(__name__)
bcrypt = Bcrypt(app)
app.secret_key = "Senai"
app.config['JWT_SECRET'] = "Senai-Chave-Secreta-Token"
app.config['IMG_FOLDER'] = 'static/img'
os.makedirs('static/img', exist_ok=True)


# ========== AUTENTICAÇÃO: FUNCIONA COM TOKEN (APP MOBILE) OU SESSÃO (SITE WEB) ==========
def usuario_logado():
    """Retorna {'usuario':..., 'tipo':...} pegando o token (app mobile) ou a sessão (site web)."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth.replace('Bearer ', '')
        try:
            dados = jwt.decode(token, app.config['JWT_SECRET'], algorithms=["HS256"])
            return {"usuario": dados.get("usuario"), "tipo": dados.get("tipo")}
        except Exception:
            return None
    if session.get('usuario'):
        return {"usuario": session.get('usuario'), "tipo": session.get('tipo')}
    return None



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


# ========== API: LISTAR ESTOQUE (usado pelo app mobile, com token) ==========
@app.route('/api/estoque')
def api_estoque():
    user = usuario_logado()
    if not user:
        return jsonify({"ok": False, "erro": "Não autenticado. Faça login novamente."}), 401

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT * FROM estoque")
    itens = cursor.fetchall()
    cursor.close()
    conexao.close()
    return jsonify(itens)


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


# ========== PAINEL ADMIN: GERENCIAR USUÁRIOS ==========
@app.route('/admin/usuarios')
def admin_usuarios():
    if session.get('tipo') != 'adm':
        return """<script>alert("Acesso restrito ao administrador!"); window.location.href = "/home";</script>"""

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT id, usuario, nome, email, tipo FROM usuario ORDER BY id DESC")
    usuarios = cursor.fetchall()
    cursor.close()
    conexao.close()
    return render_template("admin_usuarios.html", usuarios=usuarios)


# ========== LOGIN ==========
@app.route('/api/login', methods=['POST'])
def apilogin():
    dados = request.get_json()
    username = dados.get('username')
    senha = dados.get('senha')

    def gerar_token(username, tipo):
        payload = {
            "usuario": username,
            "tipo": tipo
        }
        return jwt.encode(payload, app.config['JWT_SECRET'], algorithm="HS256")

    # Login fixo de Administrador
    if username.lower() == 'admin12' and senha == 'admin1212':
        session['usuario'] = username
        session['tipo'] = 'adm'
        token = gerar_token(username, 'adm')
        return jsonify({"ok": True, "mensagem": "Login realizado com sucesso.", "token": token, "tipo": "adm"})

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    # Busca o usuário pelo nome cadastrado
    cursor.execute("SELECT * FROM usuario WHERE usuario = %s", (username,))
    usuario = cursor.fetchone()
    cursor.close()
    conexao.close()

    # Valida a senha usando a extensão flask_bcrypt
    if usuario and bcrypt.check_password_hash(usuario['senha'], senha):
        session['usuario'] = username
        # Usa o tipo cadastrado no banco (user ou adm); padrão 'user' se não definido
        tipo = usuario.get('tipo') or 'user'
        session['tipo'] = tipo
        token = gerar_token(username, tipo)
        return jsonify({"ok": True, "mensagem": "Login realizado com sucesso.", "token": token, "tipo": tipo})

    return jsonify({"ok": False, "erro": "Usuário ou senha incorretos."}), 401


# ========== ADMIN: LISTAR USUÁRIOS (usado pelo app mobile) ==========
@app.route('/api/admin/usuarios')
def api_admin_usuarios():
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso restrito ao administrador."}), 403

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT id, usuario, nome, email, tipo FROM usuario ORDER BY id DESC")
    usuarios = cursor.fetchall()
    cursor.close()
    conexao.close()
    return jsonify(usuarios)


# ========== ADMIN: CRIAR USUÁRIO OU ADMINISTRADOR ==========
@app.route('/api/admin/criarusuario', methods=['POST'])
def api_admin_criarusuario():
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso restrito ao administrador."}), 403

    dados = request.get_json() or {}
    username = (dados.get('username') or '').strip()
    senha = dados.get('senha') or ''
    nome = dados.get('nome') or None
    email = dados.get('email') or None
    tipo = dados.get('tipo', 'user')

    if tipo not in ('user', 'adm'):
        tipo = 'user'

    if not username or not senha:
        return jsonify({"ok": False, "erro": "Usuário e senha são obrigatórios."})

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT id FROM usuario WHERE usuario = %s", (username,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        conexao.close()
        return jsonify({"ok": False, "erro": "Usuário já cadastrado!"})

    senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

    cursor2 = conexao.cursor()
    cursor2.execute(
        "INSERT INTO usuario (usuario, senha, nome, email, tipo) VALUES (%s, %s, %s, %s, %s)",
        (username, senha_hash, nome, email, tipo)
    )
    conexao.commit()
    cursor2.close()
    cursor.close()
    conexao.close()

    return jsonify({"ok": True, "mensagem": f"{'Administrador' if tipo == 'adm' else 'Usuário'} '{username}' criado com sucesso!"})


# ========== ADMIN: EXCLUIR USUÁRIO ==========
@app.route('/api/admin/deletarusuario/<int:id>', methods=['DELETE'])
def api_admin_deletarusuario(id):
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso restrito ao administrador."}), 403

    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT usuario FROM usuario WHERE id = %s", (id,))
    alvo = cursor.fetchone()

    if not alvo:
        cursor.close()
        conexao.close()
        return jsonify({"ok": False, "erro": "Usuário não encontrado."})

    if alvo['usuario'] == user.get('usuario'):
        cursor.close()
        conexao.close()
        return jsonify({"ok": False, "erro": "Você não pode excluir a própria conta."})

    cursor2 = conexao.cursor()
    cursor2.execute("DELETE FROM usuario WHERE id = %s", (id,))
    conexao.commit()
    cursor2.close()
    cursor.close()
    conexao.close()
    return jsonify({"ok": True, "mensagem": f"Usuário '{alvo['usuario']}' excluído com sucesso!"})


# ========== LOGOUT ==========
@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True, "mensagem": "Sessão encerrada."})


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

    return jsonify({"ok": True, "mensagem": "Item adicionado com sucesso!"})


# ========== DELETAR ITEM DO ESTOQUE ==========
@app.route("/api/deletaritem/<int:id>", methods=["DELETE"])
def api_deletaritem(id):
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso negado."}), 403

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
    cursor2.execute(
        "INSERT INTO log_deletes (nome_admin, item, categoria, descricao, preco, qtde, estoque_min, data_delete) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (nome_admin, item['nome'], item['categoria'], item['descricao'], item['preco'], item['quantidade'], item['estoque_min'], data_delete)
    )
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
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"erro": "Acesso negado."}), 403

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
    writer.writerow(["id", "usuario", "senha"])
    cursor.execute("SELECT id, usuario, senha FROM usuario")
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
    user = usuario_logado()
    if not user or user.get('tipo') != 'adm':
        return jsonify({"ok": False, "erro": "Acesso negado."}), 403

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
                "INSERT INTO usuario (usuario, senha) VALUES (%s, %s)",
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


# ========== CHAT COM IA (GEMINI) ==========
def dados_para_ia():
    """Texto com o estoque e as últimas saídas para a IA usar nas respostas."""
    conexao = banco()
    cursor = conexao.cursor(dictionary=True)
    cursor.execute("SELECT nome, categoria, descricao, preco, quantidade, estoque_min FROM estoque ORDER BY nome")
    itens = cursor.fetchall()
    cursor.execute("SELECT item, qtde, categoria, data_hora FROM saidas ORDER BY id DESC LIMIT 30")
    saidas = cursor.fetchall()
    cursor.close()
    conexao.close()

    linhas = [f"ESTOQUE ATUAL ({len(itens)} itens):"]
    for i in itens:
        qtd = i['quantidade'] or 0
        minimo = i['estoque_min'] or 0
        aviso = " [ESTOQUE BAIXO]" if qtd <= minimo else ""
        linhas.append(
            f"- {i['nome']} | categoria: {i['categoria'] or '-'} | descrição: {i['descricao'] or '-'} | "
            f"preço: R$ {i['preco'] or 0:.2f} | quantidade: {qtd} | mínimo: {minimo}{aviso}"
        )

    linhas.append("\nÚLTIMAS SAÍDAS (da mais recente para a mais antiga):")
    for s in saidas:
        data = s['data_hora'].strftime('%d/%m/%Y %H:%M') if s['data_hora'] else 'sem data'
        linhas.append(f"- {s['item']} | quantidade: {s['qtde']} | categoria: {s['categoria'] or '-'} | {data}")
    return "\n".join(linhas)


@app.route('/api/chat', methods=['POST'])
def chat():
    if not usuario_logado():
        return jsonify({'error': 'Não autenticado. Faça login novamente.'}), 401

    dados = request.get_json(silent=True) or {}
    user_message = str(dados.get('message', '')).strip()
    if not user_message:
        return jsonify({'error': 'Mensagem vazia'}), 400

    try:
        import google.genai as genai

        chave = os.getenv("GEMINI_API_KEY")
        if not chave:
            return jsonify({'error': 'A chave GEMINI_API_KEY nao foi encontrada no arquivo .env'}), 500

        client = genai.Client(api_key=chave)
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=user_message,
            config={
                'system_instruction': (
                    'Você é um assistente virtual do sistema de almoxarifado. '
                    'Responda em português, de forma sucinta, clara e cortês. '
                    'Use os DADOS DO SISTEMA abaixo para responder sobre itens, quantidades, preços e saídas, '
                    'sem inventar: se não estiver nos dados, diga que não encontrou. '
                    '[ESTOQUE BAIXO] significa quantidade igual ou menor que o mínimo. '
                    'Você só consulta: para cadastrar, alterar ou remover itens, oriente a usar as telas do sistema.\n\n'
                    'DADOS DO SISTEMA:\n' + dados_para_ia()
                )
            }
        )
        return jsonify({'response': response.text})

    except Exception as e:
        print("ERRO NO SERVIDOR:", str(e))
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')