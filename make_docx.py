#!/usr/bin/env python3
"""Build two Japanese-summary .docx files (detailed and brief) for the
Taga et al. 2016 paper, by assembling a minimal OOXML package directly
with zipfile. No third-party dependencies."""

import os
import zipfile
from xml.sax.saxutils import escape as xml_escape

OUT_DIR = os.path.expanduser("~/Downloads")

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def para(text: str, style: str | None = None, bold: bool = False,
         size_pt: int | None = None, align: str | None = None) -> str:
    """One <w:p> with one run of text."""
    ppr_parts = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr_parts.append(f'<w:jc w:val="{align}"/>')
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""

    rpr_parts = []
    if bold:
        rpr_parts.append("<w:b/><w:bCs/>")
    if size_pt:
        half = size_pt * 2
        rpr_parts.append(f'<w:sz w:val="{half}"/><w:szCs w:val="{half}"/>')
    # Use an East-Asian-friendly font
    rpr_parts.append('<w:rFonts w:ascii="Hiragino Sans" w:eastAsia="Hiragino Sans" '
                     'w:hAnsi="Hiragino Sans"/>')
    rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>" if rpr_parts else ""

    safe = xml_escape(text).replace("\t", "    ")
    return (f"<w:p>{ppr}<w:r>{rpr}"
            f'<w:t xml:space="preserve">{safe}</w:t>'
            "</w:r></w:p>")


def heading(text: str, level: int = 1) -> str:
    size = 20 if level == 1 else 14
    return para(text, style=f"Heading{level}", bold=True, size_pt=size)


def bullet(text: str) -> str:
    # Use a simple bullet glyph; no list styling needed for readability.
    return para("・ " + text)


def build_document(blocks: list[str]) -> str:
    body = "".join(blocks)
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {W_NS}><w:body>{body}'
            f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            f'<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
            f'w:header="720" w:footer="720" w:gutter="0"/>'
            f'</w:sectPr></w:body></w:document>')


CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '</Types>')

ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" '
             'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
             'Target="word/document.xml"/></Relationships>')

DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/></Relationships>')

STYLES = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          f'<w:styles {W_NS}>'
          f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
          f'<w:name w:val="Normal"/>'
          f'<w:rPr><w:rFonts w:ascii="Hiragino Sans" w:eastAsia="Hiragino Sans" '
          f'w:hAnsi="Hiragino Sans"/><w:sz w:val="22"/></w:rPr></w:style>'
          f'<w:style w:type="paragraph" w:styleId="Heading1">'
          f'<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
          f'<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
          f'<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
          f'<w:style w:type="paragraph" w:styleId="Heading2">'
          f'<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
          f'<w:pPr><w:spacing w:before="180" w:after="80"/></w:pPr>'
          f'<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
          f'</w:styles>')


def write_docx(path: str, body_xml: str) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", body_xml)


# ----------------------------------------------------------------------
# Detailed Japanese summary (paraphrased, ~A4 3–4 pages)
# ----------------------------------------------------------------------

detailed_blocks = []
a = detailed_blocks.append

a(para("多エージェント方式による帰宅経路支援システムのシミュレーション",
       bold=True, size_pt=18, align="center"))
a(para("— Taga, Matsuzawa, Takimoto, Kambayashi (ICAART 2016) の日本語要約 —",
       align="center"))
a(para("※ 本書は原著論文の全文翻訳ではなく、構成を保った要約です。原典："
       "S. Taga, T. Matsuzawa, M. Takimoto, Y. Kambayashi, "
       "\"Multi-agent Approach for Return Route Support System Simulation,\" "
       "ICAART 2016, Vol.1, pp.269–274, DOI: 10.5220/0005819602690274。"))

a(heading("1. 背景と問題設定"))
a(para(
    "2011 年の東日本大震災では、震源から 300 km 以上離れた東京においても地盤の"
    "液状化や通信基盤の故障が発生し、公共交通は停止、スマートフォンによるネット"
    "検索もメール受信も困難になった。多くの帰宅困難者は情報源を失い、徒歩で自宅"
    "を目指さざるを得なかった。現代人はナビや地図アプリに依存しているため、"
    "災害時にインターネット前提の情報源を失うと二次災害リスクが跳ね上がる。"))
a(para(
    "既存の帰宅支援アプリ（例：Mapple ON）は事前の道路ネットワーク情報を用いる"
    "ため、災害後に通行不可となった経路を避ける判断ができない。したがって、"
    "通信基盤に依存せず、リアルタイムの道路状況を反映できる仕組みが必要である。"))

a(heading("2. 提案システムの骨子"))
a(para(
    "提案システムは、利用者のスマートフォン同士が MANET（モバイルアドホック"
    "ネットワーク）を一時的に形成し、モバイルエージェントを介して通行不可点や"
    "救護所などの情報を共有する。Wi-Fi を用いた端末間直接通信を利用し、基地局に"
    "依存しない。地図情報は災害発生前にあらかじめ登録しておく前提である。"))
a(para(
    "経路導出には Dijkstra 法を用い、交差点をノードとしてグラフ化する。"
    "利用者がリアルタイムに取得した不通点を反映して経路を再計算することで、"
    "事前地図だけでは対応できない状況に追随する。"))

a(heading("3. エージェント構成"))
a(para(
    "本システムは 2 種 4 役のエージェントで構成される。"))
a(bullet("IA（Information Agent, 静的）: ユーザインタフェースを司り、地図に経路と"
         "既知の不通点や救護所を表示する。ユーザの拡散ボタン押下で IDA を生成し、"
         "また一定間隔で RA を生成して情報収集を行う。"))
a(bullet("NA（Node Management Agent, 静的）: IA が収集した情報（位置、不通点、"
         "救護所、休憩所、各 IDA の ID、時刻）を保持し、IA の要求に応じて提供する。"
         "重複情報は時刻でフィルタし、一定時間経過後には古い情報を削除する。"))
a(bullet("RA（Routing Agent, モバイル）: IA が生成し、目的地方向のスマートフォンを"
         "辿って情報を集める偵察役。訪問履歴を持ち、一定ホップ数を渡り終えると履歴を"
         "逆順に辿って発信元へ戻る。リンク切れで戻れないときは自己消滅する。"))
a(bullet("IDA（Information Diffusion Agent, モバイル）: 新規発見の通行不可点や"
         "救護所の情報を周囲に拡散する。発信元は近傍の各端末へ IDA を複製して送り、"
         "受信側もさらに周辺に複製を送る。同一 ID を持つ IDA が到着済みの端末では"
         "自己消滅し、重複拡散を防ぐ。"))
a(para(
    "IDA は Ant Colony Optimization のフェロモンに相当し、発見点からの距離・移動"
    "ホップ数・経過時間が増えるほど情報価値を下げ、閾値を下回ると消える。"
    "RA は IDA の痕跡（= フェロモン）に引き寄せられる形で経路を探索する。"))

a(heading("4. 予備評価"))
a(para(
    "提案方式の実現可能性を確認するため、著者らはシミュレータを構築した。"
    "画面上では利用者（赤点）、通行不可点（紫領域）、安全域（緑領域）、端末間リンク"
    "（線）が描画される。各スマホのバッテリは乱数で与えられ、切れると停止する。"
    "通信範囲に入った端末同士は自動的にリンクされる。視認範囲に入った利用者が"
    "不通点を発見すると IDA で位置情報を拡散する。"))
a(para(
    "実験条件：利用者 300 名、フィールド 800×625 画素、1 ラウンドあたり 2 画素移動。"
    "「全員がシステムを搭載」した場合と「誰も搭載していない」場合を各 10 回実行し、"
    "全員が安全域に到達するまでの平均ラウンド数を比較した。"))
a(para(
    "結果：システム有で 583 ラウンド、システム無で 683 ラウンド。事前に不通点を"
    "知ってから動ける利用者の方が早く到達するという予測どおりの傾向が得られた。"))

a(heading("5. 考察と今後の課題"))
a(para(
    "予備実験では有効性が示されたが、現実運用に向けては課題が多い。"))
a(bullet("端末資源の制約: 不通点を多く発見すると IDA が大量発生し、各端末の計算・"
         "電池負荷が増す。流入制御の閾値を IA が動的に決めると IA 自体が重くなるため、"
         "事前設定の方が現実的だが環境ごとの最適値決定は今後の課題。"))
a(bullet("RA の帰還失敗: 現状の RA は訪問履歴を逆順に辿る。途中の端末が移動・停止・"
         "電池切れで消えると帰還できない。対策として、目的地近傍で別端末の接続情報を"
         "取得し代替ルートで戻る案があるが、RA の負荷増とトレードオフである。"))
a(bullet("端末の任意停止: 実際には電池節約のため利用者自身が端末電源を落とす可能性"
         "があり、シミュレータの前提（到達か電池切れまで稼働）より RA 喪失率は高い。"))
a(para(
    "関連研究として、複数センサ連携に関する Stranders らの分散協調アルゴリズムや、"
    "Zambonelli らの SAPERE プロジェクトなど、コンテキスト対応のサービス生態系に"
    "関する研究があり、今後これらの知見と統合する計画である。"))

a(heading("6. 結論"))
a(para(
    "通信インフラが麻痺した災害下において、スマホ群による MANET とモバイル"
    "エージェントで経路情報を共有する帰宅支援システムを提案し、予備的な"
    "シミュレーションでその有効性（有 vs 無で 583 対 683 ラウンド）を確認した。"
    "今後はシミュレータの精緻化、特に人流の動的感知を含む拡張を進める。"))

write_docx(os.path.join(OUT_DIR, "drone_paper_summary_detailed.docx"),
           build_document(detailed_blocks))

# ----------------------------------------------------------------------
# Brief Japanese summary (A4 1 page)
# ----------------------------------------------------------------------

brief_blocks = []
b = brief_blocks.append

b(para("帰宅経路支援システムのマルチエージェント・シミュレーション — 要約版",
       bold=True, size_pt=16, align="center"))
b(para("Taga et al., ICAART 2016 の要点整理（原文の章立てに沿った日本語要約）",
       align="center"))

b(heading("背景", level=2))
b(para(
    "大規模災害時は通信基盤と公共交通が麻痺し、帰宅困難者はネットを使った経路探索"
    "や状況確認ができない。既存の帰宅支援アプリは事前地図のみを用い、災害後の"
    "不通点に追随できない。"))

b(heading("手法", level=2))
b(para(
    "端末間で MANET を一時的に構築し、モバイルエージェントで経路情報を共有する。"))
b(bullet("IA（情報エージェント, 静的）: UI 担当。RA と IDA を生成・回収。"))
b(bullet("NA（ノード管理, 静的）: 収集情報の保持と重複除去。"))
b(bullet("RA（経路探索, モバイル）: 目的地方向の端末を辿り情報を収集し戻る。"))
b(bullet("IDA（情報拡散, モバイル）: 新発見の不通点を周辺端末に複製拡散。"
         "距離・ホップ・時間で価値減衰する ACO フェロモン相当。"))
b(para("経路導出は交差点ノード上の Dijkstra 法。新規の不通点情報を受けると再計算。"))

b(heading("実験", level=2))
b(para(
    "300 ユーザ・フィールド 800×625 画素・1 ラウンド 2 画素移動。"
    "「システム有」「システム無」各 10 試行で全員の到達までの平均ラウンドを比較。"))
b(para("結果: 有 583 ラウンド / 無 683 ラウンド。事前に不通点を知る効果を確認。",
       bold=True))

b(heading("課題", level=2))
b(bullet("IDA 過多による端末負荷 → 流入閾値設計が必要。"))
b(bullet("RA の帰還失敗 → 代替ルート機構の導入と負荷のトレードオフ。"))
b(bullet("利用者が電池節約で任意に端末を停止 → 現実の RA 喪失率は実験より高い。"))

b(heading("結論", level=2))
b(para(
    "MANET とモバイルエージェントによる帰宅支援は、予備実験で有効性を示した。"
    "今後は人流の動的感知を含むシミュレータ拡張と関連研究との統合を進める。"))

write_docx(os.path.join(OUT_DIR, "drone_paper_summary_brief.docx"),
           build_document(brief_blocks))

print("wrote:")
for f in ("drone_paper_summary_detailed.docx", "drone_paper_summary_brief.docx"):
    p = os.path.join(OUT_DIR, f)
    print(f"  {p}  ({os.path.getsize(p)} bytes)")
