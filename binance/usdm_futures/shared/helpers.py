from pathlib import Path


def mark_toml_as_invalid(filepath: str) -> str:
    """Renomeia o arquivo TOML adicionando sufixo '.invalid'.

    Usado quando a configuração do par é incompatível com a conta (símbolo
    inexistente, leverage acima do máximo, credencial rejeitada). O sufixo
    permite identificar o arquivo problemático por listagem do diretório.
    """
    path = Path(filepath)
    new_path = path.with_name(f"{path.name}.invalid")
    path.rename(new_path)
    return str(new_path)
