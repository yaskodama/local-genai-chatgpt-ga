#!/usr/bin/env python3
import html
import os
import zipfile


OUT = "docs/TYPED_AI_AGENT_LANGUAGE_PAPER_SLIDES.pptx"
EMU_W = 12192000
EMU_H = 6858000


def esc(text):
    return html.escape(text, quote=True)


def emu(x):
    return int(x)


def text_shape(shape_id, x, y, w, h, lines, font_size=2400, bold=False,
               color="202124", fill=None, align="l"):
    if isinstance(lines, str):
        lines = [lines]
    fill_xml = ""
    if fill:
        fill_xml = (
            "<a:solidFill><a:srgbClr val=\"%s\"/></a:solidFill>"
            % fill
        )
    paras = []
    for i, line in enumerate(lines):
        paras.append(
            "<a:p><a:pPr algn=\"%s\"/>"
            "<a:r><a:rPr lang=\"ja-JP\" sz=\"%d\" %s>"
            "<a:solidFill><a:srgbClr val=\"%s\"/></a:solidFill>"
            "<a:latin typeface=\"Yu Gothic\"/><a:ea typeface=\"Yu Gothic\"/>"
            "</a:rPr><a:t>%s</a:t></a:r></a:p>"
            % (
                align,
                font_size if i == 0 else max(font_size - 200, 1600),
                "b=\"1\"" if bold else "",
                color,
                esc(line),
            )
        )
    return f"""
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="{shape_id}" name="TextBox {shape_id}"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          {fill_xml}
          <a:ln><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" lIns="80000" tIns="50000" rIns="80000" bIns="50000"/>
          <a:lstStyle/>
          {''.join(paras)}
        </p:txBody>
      </p:sp>
    """


def bullet_shape(shape_id, x, y, w, h, bullets, font_size=2200):
    paras = []
    for bullet in bullets:
        paras.append(
            "<a:p><a:pPr marL=\"260000\" indent=\"-180000\">"
            "<a:buChar char=\"•\"/></a:pPr>"
            "<a:r><a:rPr lang=\"ja-JP\" sz=\"%d\">"
            "<a:solidFill><a:srgbClr val=\"202124\"/></a:solidFill>"
            "<a:latin typeface=\"Yu Gothic\"/><a:ea typeface=\"Yu Gothic\"/>"
            "</a:rPr><a:t>%s</a:t></a:r></a:p>"
            % (font_size, esc(bullet))
        )
    return f"""
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="{shape_id}" name="Bullets {shape_id}"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:ln><a:noFill/></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" lIns="60000" tIns="40000" rIns="60000" bIns="40000"/>
          <a:lstStyle/>
          {''.join(paras)}
        </p:txBody>
      </p:sp>
    """


def rect_shape(shape_id, x, y, w, h, text, fill="EEF2FF", line="4A67D6",
               font_size=1900):
    return f"""
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="{shape_id}" name="Box {shape_id}"/>
          <p:cNvSpPr/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
          <a:ln w="16000"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" anchor="ctr"/>
          <a:lstStyle/>
          <a:p><a:pPr algn="ctr"/>
            <a:r><a:rPr lang="ja-JP" sz="{font_size}" b="1">
              <a:solidFill><a:srgbClr val="202124"/></a:solidFill>
              <a:latin typeface="Yu Gothic"/><a:ea typeface="Yu Gothic"/>
            </a:rPr><a:t>{esc(text)}</a:t></a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    """


def slide_xml(title, body_shapes):
    header = text_shape(10, 520000, 220000, 11100000, 650000, title,
                        font_size=3000, bold=True, color="17324D")
    footer = text_shape(11, 540000, 6400000, 6000000, 260000,
                        "型付きAIエージェント記述言語の設計と実装",
                        font_size=1100, color="5F6368")
    shapes = header + "".join(body_shapes) + footer
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
      {shapes}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def title_slide():
    return slide_xml("", [
        text_shape(20, 700000, 900000, 10800000, 1300000,
                   ["型付きAIエージェント記述言語の設計と実装"],
                   font_size=3800, bold=True, color="17324D", align="ctr"),
        text_shape(21, 1900000, 2400000, 8400000, 650000,
                   ["AIPL: Actor-based Intelligent Parallel Language"],
                   font_size=2200, color="3C4043", align="ctr"),
        text_shape(22, 2200000, 4050000, 7800000, 850000,
                   ["児玉靖司（Yasushi Kodama）", "法政大学（Hosei University）"],
                   font_size=2100, color="202124", align="ctr"),
        text_shape(23, 4100000, 5300000, 3900000, 420000,
                   "2026年5月12日", font_size=1600, color="5F6368", align="ctr"),
    ])


SLIDES = [
    title_slide(),
    slide_xml("背景と問題意識", [
        bullet_shape(20, 950000, 1250000, 10300000, 4300000, [
            "生成AIアプリは自然言語、外部API、ファイル、ネットワーク、並行タスクを組み合わせる",
            "AI呼び出しが通常の関数やHTTPラッパに埋もれると、同期点・権限・失敗時処理が見えにくい",
            "複数AIエージェントの協調では、メッセージの流れとデータ所有権を明示する必要がある",
            "本研究はAIエージェントを型付きアクターとして記述する言語を設計する",
        ]),
    ]),
    slide_xml("研究の貢献", [
        bullet_shape(20, 950000, 1300000, 10300000, 4200000, [
            "AIエージェントをアクターとして記述する AIPL の言語設計",
            "send / now / future / await による同期・非同期通信の統一",
            "型、効果、所有権、線形性、構造化並行を段階的に導入",
            "OCaml、Python、JavaScript、C の複数処理系による実装と比較",
        ]),
    ]),
    slide_xml("AIPLの基本モデル", [
        rect_shape(20, 850000, 1600000, 2300000, 900000, "User Actor", "E8F0FE"),
        text_shape(21, 3300000, 1750000, 800000, 450000, "send", 1700, True, "4A67D6", align="ctr"),
        rect_shape(22, 4250000, 1600000, 2500000, 900000, "Worker Actor", "E6F4EA", "188038"),
        text_shape(23, 7050000, 1750000, 900000, 450000, "future", 1700, True, "4A67D6", align="ctr"),
        rect_shape(24, 8150000, 1600000, 2600000, 900000, "AI Actor", "FEF7E0", "F29900"),
        bullet_shape(25, 1150000, 3300000, 9600000, 1700000, [
            "各 class のインスタンスがメールボックスを持つアクターとして実行される",
            "now は reply を待つ同期呼び出し、future は後続の await で結果を取得する",
            "AI呼び出しもアクター通信の一部として扱う",
        ], font_size=2000),
    ]),
    slide_xml("言語機能", [
        bullet_shape(20, 850000, 1250000, 5200000, 4300000, [
            "class / method / var によるアクター定義",
            "send: 非同期メッセージ送信",
            "now: 返信を待つ同期呼び出し",
            "future / await: 遅延結果の明示",
            "become: 実行中の振る舞い変更",
        ], font_size=1900),
        bullet_shape(21, 6450000, 1250000, 5200000, 4300000, [
            "ai_call 系の組み込み関数",
            "AIアクターとしての ask/reply",
            "動的コンパイルと spawn",
            "メソッドインジェクション",
            "mock provider によるオフライン検証",
        ], font_size=1900),
    ]),
    slide_xml("型システム", [
        bullet_shape(20, 900000, 1250000, 10300000, 4300000, [
            "基本型: int, float, string, bool",
            "構造型: array[T], tuple, record, Union, 型変数, 長さ付き配列",
            "未注釈領域は any として扱う段階的型付け",
            "transient cast により any から具体型へ入る境界を実行時検査",
            "注釈された領域の局所的安全性を重視する",
        ]),
    ]),
    slide_xml("AI効果・所有権・線形型", [
        bullet_shape(20, 900000, 1250000, 10300000, 4300000, [
            "Capability 効果: !{ai}, !{fs}, !{net}, !{mut}",
            "AI呼び出しや外部I/Oをメソッド型に明示する",
            "pub フィールドにより公開状態と内部状態を分離する",
            "linear T により move 後の再利用を検出する",
            "APIキー、セッション、外部資源の誤用防止に向く",
        ]),
    ]),
    slide_xml("実装構成", [
        rect_shape(20, 700000, 1300000, 2300000, 900000, "OCaml版\n基礎実行", "E8F0FE"),
        rect_shape(21, 3450000, 1300000, 2300000, 900000, "Python版\n研究機能", "E6F4EA", "188038"),
        rect_shape(22, 6200000, 1300000, 2300000, 900000, "JS版\nブラウザ", "FEF7E0", "F29900"),
        rect_shape(23, 8950000, 1300000, 2300000, 900000, "C版\npthread/SDL2", "FCE8E6", "D93025"),
        bullet_shape(24, 1050000, 3100000, 9700000, 1900000, [
            "OCaml版: パーサ、型推論、Threadランタイム、リモート/SDL/Web gateway",
            "Python版: 型注釈、効果、線形型、所有権、モデル検査、AI連携",
            "JS版: ブラウザ内実行とCanvas可視化",
            "C版: POSIX pthread、SDL2 GUI、Xinu風環境へのコード生成",
        ], font_size=1750),
    ]),
    slide_xml("評価: サンプルプログラム", [
        bullet_shape(20, 900000, 1200000, 10300000, 4450000, [
            "Counter / PingPong: 基本的なアクター生成、送信、返信",
            "Bounded Buffer: 生産者・消費者、同期、キュー状態の可視化",
            "Dining Philosophers: 資源獲得、競合、デッドロック観察",
            "Line Rotation: GUI描画、周期実行、C/SDL2変換",
            "AI samples: プロンプト、AI呼び出し、mock provider による検証",
        ]),
    ]),
    slide_xml("議論", [
        bullet_shape(20, 900000, 1250000, 10300000, 4300000, [
            "AI応答は非決定的であり、型だけで内容の正しさを保証することはできない",
            "一方で、AIを呼ぶ場所、渡すデータ、同期点、権限は言語機能として明示できる",
            "動的コンパイルと型検査は矛盾ではなく、検査境界を明示する設計として共存する",
            "AIPLは閉じた世界の完全性より、AI生成コードを扱うための監査可能性を重視する",
        ]),
    ]),
    slide_xml("現時点の制限", [
        bullet_shape(20, 900000, 1250000, 10300000, 4300000, [
            "処理系間で実装済み機能に差がある",
            "Python版のPhase 11以降の型付き構文はOCaml版で直接扱えない",
            "C変換では become や select の一部に制限がある",
            "ブラウザ実行では file:// よりローカルサーバ経由が安定する",
            "共通中間表現と形式的意味論の整備が今後の課題である",
        ]),
    ]),
    slide_xml("まとめと今後の課題", [
        bullet_shape(20, 900000, 1200000, 10300000, 4400000, [
            "AIPLはAIエージェントを型付きアクターとして記述する研究言語である",
            "通信、AI呼び出し、型、効果、所有権、構造化並行を同一モデルに統合した",
            "複数処理系により、研究用実行、ブラウザ可視化、C変換を比較できる",
            "今後は共通仕様、型健全性の範囲、AI応答契約、権限モデルを整備する",
        ]),
        text_shape(21, 3800000, 5750000, 4400000, 420000,
                   "ご清聴ありがとうございました", 1900, True, "17324D", align="ctr"),
    ]),
]


def content_types(nslides):
    overrides = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for i in range(1, nslides + 1):
        overrides.append(
            f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' + "".join(overrides) + "</Types>"


def rels_root():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def presentation_xml(nslides):
    slide_ids = []
    for i in range(1, nslides + 1):
        slide_ids.append(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>')
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>{''.join(slide_ids)}</p:sldIdLst>
  <p:sldSz cx="{EMU_W}" cy="{EMU_H}" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>
"""


def presentation_rels(nslides):
    rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
    for i in range(1, nslides + 1):
        rels.append(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rels) + "</Relationships>"


SLIDE_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>
"""


SLIDE_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"""


SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld name="Blank"><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"""


SLIDE_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""


THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="AIPL Theme">
  <a:themeElements>
    <a:clrScheme name="AIPL">
      <a:dk1><a:srgbClr val="202124"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="17324D"/></a:dk2><a:lt2><a:srgbClr val="F8F9FA"/></a:lt2>
      <a:accent1><a:srgbClr val="4A67D6"/></a:accent1>
      <a:accent2><a:srgbClr val="188038"/></a:accent2>
      <a:accent3><a:srgbClr val="F29900"/></a:accent3>
      <a:accent4><a:srgbClr val="D93025"/></a:accent4>
      <a:accent5><a:srgbClr val="9334E6"/></a:accent5>
      <a:accent6><a:srgbClr val="00ACC1"/></a:accent6>
      <a:hlink><a:srgbClr val="1155CC"/></a:hlink><a:folHlink><a:srgbClr val="5E35B1"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="AIPL">
      <a:majorFont><a:latin typeface="Yu Gothic"/><a:ea typeface="Yu Gothic"/><a:cs typeface="Arial"/></a:majorFont>
      <a:minorFont><a:latin typeface="Yu Gothic"/><a:ea typeface="Yu Gothic"/><a:cs typeface="Arial"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="AIPL"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>
"""


def core_props():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>型付きAIエージェント記述言語の設計と実装</dc:title>
  <dc:creator>児玉靖司（Yasushi Kodama）</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
</cp:coreProperties>
"""


def app_props(nslides):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft PowerPoint</Application>
  <PresentationFormat>Widescreen</PresentationFormat>
  <Slides>{nslides}</Slides>
</Properties>
"""


def empty_rels():
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        n = len(SLIDES)
        z.writestr("[Content_Types].xml", content_types(n))
        z.writestr("_rels/.rels", rels_root())
        z.writestr("docProps/core.xml", core_props())
        z.writestr("docProps/app.xml", app_props(n))
        z.writestr("ppt/presentation.xml", presentation_xml(n))
        z.writestr("ppt/_rels/presentation.xml.rels", presentation_rels(n))
        z.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS)
        z.writestr("ppt/theme/theme1.xml", THEME)
        for i, slide in enumerate(SLIDES, 1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide)
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", empty_rels())
    print(OUT)


if __name__ == "__main__":
    main()
