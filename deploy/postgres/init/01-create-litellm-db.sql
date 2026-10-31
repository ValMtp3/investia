-- Base dédiée à LiteLLM sur le même serveur PostgreSQL (D10 : un seul serveur, plusieurs bases).
SELECT 'CREATE DATABASE litellm'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec
