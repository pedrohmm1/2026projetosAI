from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import os
import requests

app = Flask(__name__)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
USER_API_URL = os.getenv("USER_API_URL", "http://18.228.48.67/users")

client = MongoClient(MONGO_URL)
db = client["pagamentos_db"]
pagamentos_collection = db["pagamentos"]


def serialize_pagamento(pagamento):
    return {
        "id": str(pagamento["_id"]),
        "cliente_id": pagamento["cliente_id"],
        "cliente_email": pagamento["cliente_email"],
        "codigo_pagamento": pagamento["codigo_pagamento"],
        "valor_total": pagamento["valor_total"],
        "tipo_pagamento": pagamento["tipo_pagamento"],
        "numero_parcelas": pagamento["numero_parcelas"],
        "valor_parcela": pagamento["valor_parcela"],
        "data_pagamento": pagamento["data_pagamento"]
    }


def calcular_valor_parcela(valor_total, numero_parcelas):
    valor = Decimal(str(valor_total))
    parcelas = Decimal(str(numero_parcelas))
    valor_parcela = (valor / parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(valor_parcela)


def buscar_usuario(cliente_id):
    response = requests.get(f"{USER_API_URL}/{cliente_id}", timeout=5)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


@app.route("/", methods=["GET"])
def home():
    return jsonify({"mensagem": "API de pagamentos online"}), 200


@app.route("/pagamento", methods=["GET"])
def listar_pagamentos():
    cliente_id = request.args.get("cliente_id")

    if cliente_id:
        pagamentos = pagamentos_collection.find({"cliente_id": cliente_id})
    else:
        pagamentos = pagamentos_collection.find()

    lista = [serialize_pagamento(pagamento) for pagamento in pagamentos]
    return jsonify(lista), 200


@app.route("/pagamento/<id>", methods=["DELETE"])
def deletar_pagamento(id):
    try:
        object_id = ObjectId(id)
    except InvalidId:
        return jsonify({"erro": "Pagamento não encontrado"}), 404

    pagamento = pagamentos_collection.find_one({"_id": object_id})

    if not pagamento:
        return jsonify({"erro": "Pagamento não encontrado"}), 404

    pagamentos_collection.delete_one({"_id": object_id})
    return jsonify({"mensagem": "Pagamento deletado com sucesso"}), 200


@app.route("/pagamento", methods=["POST"])
def criar_pagamento():
    data = request.get_json()

    if not data:
        return jsonify({"erro": "Body JSON obrigatório"}), 400

    campos_obrigatorios = [
        "cliente_id",
        "codigo_pagamento",
        "valor_total",
        "tipo_pagamento",
        "numero_parcelas",
        "data_pagamento"
    ]

    for campo in campos_obrigatorios:
        if campo not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    cliente_id = str(data["cliente_id"])
    codigo_pagamento = str(data["codigo_pagamento"])

    try:
        valor_total = float(data["valor_total"])
    except (ValueError, TypeError):
        return jsonify({"erro": "valor_total inválido"}), 400

    try:
        numero_parcelas = int(data["numero_parcelas"])
    except (ValueError, TypeError):
        return jsonify({"erro": "numero_parcelas inválido"}), 400

    tipo_pagamento = str(data["tipo_pagamento"])

    if tipo_pagamento not in ["PIX", "Credito"]:
        return jsonify({"erro": "tipo_pagamento deve ser PIX ou Credito"}), 400

    if valor_total <= 0:
        return jsonify({"erro": "valor_total deve ser maior que zero"}), 400

    if numero_parcelas <= 0:
        return jsonify({"erro": "numero_parcelas deve ser maior que zero"}), 400

    try:
        datetime.strptime(data["data_pagamento"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"erro": "data_pagamento deve estar no formato YYYY-MM-DD"}), 400

    pagamento_existente = pagamentos_collection.find_one({"codigo_pagamento": codigo_pagamento})
    if pagamento_existente:
        return jsonify({"erro": "codigo_pagamento já cadastrado"}), 400

    try:
        usuario = buscar_usuario(cliente_id)
    except requests.RequestException:
        return jsonify({"erro": "Erro ao consultar API de usuários"}), 503

    if not usuario:
        return jsonify({"erro": "Usuário não encontrado"}), 404

    cliente_email = usuario.get("email")
    if not cliente_email:
        return jsonify({"erro": "Email do usuário não encontrado na API externa"}), 502

    valor_parcela = calcular_valor_parcela(valor_total, numero_parcelas)

    novo_pagamento = {
        "cliente_id": cliente_id,
        "cliente_email": cliente_email,
        "codigo_pagamento": codigo_pagamento,
        "valor_total": valor_total,
        "tipo_pagamento": tipo_pagamento,
        "numero_parcelas": numero_parcelas,
        "valor_parcela": valor_parcela,
        "data_pagamento": data["data_pagamento"]
    }

    resultado = pagamentos_collection.insert_one(novo_pagamento)
    novo_pagamento["_id"] = resultado.inserted_id

    return jsonify(serialize_pagamento(novo_pagamento)), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)