"""Gera o ícone do executável (icone.ico) e a versão em PNG.

    uv run --group build python packaging/gerar_icone.py

O desenho é feito numa tela 4x maior e reduzido no fim, o que dá borda
suave sem depender de antialiasing do ImageDraw. O `.ico` sai com entradas
em BMP (formato clássico), que é o que o Windows espera em executáveis.

O conceito é uma folha fiscal em branco sobre um quadrado azul, com as três
cores das categorias (entrada, saida e não classificado) desenhadas como
barras de conteúdo.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parent
MASTER = 512
ESCALA = 4
LADO = MASTER * ESCALA

# paleta
AZUL_TOPO = (59, 130, 246)
AZUL_BASE = (23, 63, 168)
BRANCO = (255, 255, 255)
VINTA = (222, 233, 250)
BARRAS = ((37, 99, 235), (13, 148, 136), (245, 158, 11))
SOMBRA = (12, 34, 88)


def p(valor: float) -> int:
    """Converte da escala do master (512) para a tela supersamplada."""
    return int(round(valor * ESCALA))


def fundo() -> Image.Image:
    """Quadrado arredondado com gradiente vertical."""
    gradiente = Image.new("RGB", (1, LADO))
    pixels = gradiente.load()
    for y in range(LADO):
        t = y / (LADO - 1)
        pixels[0, y] = tuple(
            round(c1 + (c2 - c1) * t) for c1, c2 in zip(AZUL_TOPO, AZUL_BASE)
        )
    gradiente = gradiente.resize((LADO, LADO))

    mascara = Image.new("L", (LADO, LADO), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, LADO - 1, LADO - 1], radius=p(108), fill=255
    )

    base = Image.composite(gradiente.convert("RGBA"), Image.new("RGBA", (LADO, LADO)), mascara)

    # brilho suave no canto superior esquerdo
    brilho = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).ellipse(
        [-p(160), -p(220), p(430), p(300)], fill=(255, 255, 255, 70)
    )
    brilho = brilho.filter(ImageFilter.GaussianBlur(p(70)))
    base = Image.alpha_composite(base, Image.composite(brilho, Image.new("RGBA", (LADO, LADO)), mascara))
    return base


def folha() -> Image.Image:
    """Folha de papel com a dobra no canto e as barras de conteúdo."""
    x0, y0, x1, y1 = p(128), p(96), p(384), p(400)
    dobra = p(78)

    sombra = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle(
        [x0, y0 + p(14), x1, y1 + p(14)], radius=p(14), fill=SOMBRA + (110,)
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(p(16)))

    papel = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(papel)
    desenho.polygon(
        [(x0, y0), (x1 - dobra, y0), (x1, y0 + dobra), (x1, y1), (x0, y1)],
        fill=BRANCO + (255,),
    )
    # a aba dobrada: triângulo claro no canto
    desenho.polygon(
        [(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)],
        fill=VINTA + (255,),
    )

    barras = ImageDraw.Draw(papel)
    largura_x = p(172)
    for indice, (cor, largura) in enumerate(zip(BARRAS, (170, 128, 152))):
        topo = p(206) + indice * p(58)
        barras.rounded_rectangle(
            [largura_x, topo, largura_x + p(largura), topo + p(26)],
            radius=p(13),
            fill=cor + (255,),
        )

    return Image.alpha_composite(sombra, papel)


def construir() -> Image.Image:
    return Image.alpha_composite(fundo(), folha()).resize(
        (MASTER, MASTER), Image.LANCZOS
    )


def main() -> None:
    imagem = construir()

    icone = RAIZ / "icone.ico"
    imagem.save(
        icone,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
               (64, 64), (96, 96), (128, 128), (256, 256)],
        bitmap_format="bmp",
    )

    previa = RAIZ / "icone.png"
    imagem.save(previa, format="PNG")

    print(f"ícone gerado: {icone} ({icone.stat().st_size:,} bytes)")
    print(f"prévia: {previa}")


if __name__ == "__main__":
    main()
