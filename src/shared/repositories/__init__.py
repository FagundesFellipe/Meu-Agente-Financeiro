"""Repositórios de acesso a dados — uma função por consulta, sem lógica de negócio.

Todo repositório que toca tabela financeira recebe ``user_id`` e usa
``shared.db.user_connection`` para ativar o isolamento por Row-Level Security.
"""
