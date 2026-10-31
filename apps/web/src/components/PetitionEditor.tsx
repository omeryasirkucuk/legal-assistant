"use client";

// The petition on an A4 sheet, edited like a word processor: undo, size, bold, italic,
// underline, alignment and lists in a toolbar above it. Citation markers show as small
// numbered chips that cannot be typed over; files leave them out. What is set here is what
// the Word, PDF and UDF files show.
import { useEffect } from "react";
import { EditorContent, useEditor, type Editor, type JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import TextStyle from "@tiptap/extension-text-style";
import {
  AlignCenter, AlignJustify, AlignLeft, AlignRight, Bold, Italic, List, ListOrdered, Redo2,
  Underline as UnderlineIcon, Undo2,
} from "lucide-react";
import type { EditorDoc } from "@/lib/api";
import { Citation, FontSize } from "@/lib/editor/extensions";
import { t, type MessageKey } from "@/lib/i18n";

/** The editor's schema; also used to show a document read-only (generateHTML). */
export const EXTENSIONS = [
  StarterKit.configure({ heading: false, codeBlock: false, code: false, blockquote: false,
                         horizontalRule: false, strike: false }),
  Underline,
  TextStyle,
  FontSize,
  TextAlign.configure({ types: ["paragraph"], alignments: ["left", "center", "right", "justify"],
                        defaultAlignment: "justify" }),
  Citation,
];

const SIZES = ["10", "11", "12", "13", "14", "16", "18", "20"];
const BODY_SIZE = "12";

/** The selected passage as the draft's text has it (citation chips as [[E#]]). */
export function selectedText(editor: Editor): string {
  const { from, to } = editor.state.selection;
  if (from === to) return "";
  return editor.state.doc.textBetween(from, to, "\n\n", (node) =>
    node.type.name === "citation" ? `[[${node.attrs.key}]]` : "");
}

function Tool({ label, active, disabled, onClick, children }: {
  label: MessageKey; active?: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={onClick} disabled={disabled}
      aria-label={t(label)} title={t(label)} aria-pressed={active}
      className={`flex h-8 w-8 items-center justify-center rounded-md pointer-coarse:h-10 pointer-coarse:w-10 disabled:opacity-30 ${
        active ? "bg-ink text-white" : "text-ink hover:bg-paper"}`}>
      {children}
    </button>
  );
}

function Divider() {
  return <span className="mx-1 h-5 w-px bg-rule" aria-hidden />;
}

function Toolbar({ editor, disabled }: { editor: Editor; disabled: boolean }) {
  const size = String(editor.getAttributes("textStyle").fontSize ?? "").replace("pt", "") || BODY_SIZE;
  const c = () => editor.chain().focus();
  const align = (a: string) => editor.isActive({ textAlign: a });
  return (
    <div role="toolbar" aria-label={t("editorToolbar")}
      className="flex flex-wrap items-center gap-0.5 border-b border-rule bg-sheet px-3 py-1.5">
      <Tool label="editorUndo" disabled={disabled || !editor.can().undo()} onClick={() => c().undo().run()}><Undo2 size={16} /></Tool>
      <Tool label="editorRedo" disabled={disabled || !editor.can().redo()} onClick={() => c().redo().run()}><Redo2 size={16} /></Tool>
      <Divider />
      <select value={SIZES.includes(size) ? size : BODY_SIZE} disabled={disabled} aria-label={t("editorSize")} title={t("editorSize")}
        onChange={(e) => (e.target.value === BODY_SIZE ? c().unsetFontSize().run() : c().setFontSize(`${e.target.value}pt`).run())}
        className="h-8 rounded-md border border-rule bg-sheet px-1.5 text-sm tabular-nums text-ink outline-none focus:border-cite">
        {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <Divider />
      <Tool label="editorBold" active={editor.isActive("bold")} disabled={disabled} onClick={() => c().toggleBold().run()}><Bold size={16} /></Tool>
      <Tool label="editorItalic" active={editor.isActive("italic")} disabled={disabled} onClick={() => c().toggleItalic().run()}><Italic size={16} /></Tool>
      <Tool label="editorUnderline" active={editor.isActive("underline")} disabled={disabled} onClick={() => c().toggleUnderline().run()}><UnderlineIcon size={16} /></Tool>
      <Divider />
      <Tool label="editorAlignLeft" active={align("left")} disabled={disabled} onClick={() => c().setTextAlign("left").run()}><AlignLeft size={16} /></Tool>
      <Tool label="editorAlignCenter" active={align("center")} disabled={disabled} onClick={() => c().setTextAlign("center").run()}><AlignCenter size={16} /></Tool>
      <Tool label="editorAlignRight" active={align("right")} disabled={disabled} onClick={() => c().setTextAlign("right").run()}><AlignRight size={16} /></Tool>
      <Tool label="editorAlignJustify" active={align("justify")} disabled={disabled} onClick={() => c().setTextAlign("justify").run()}><AlignJustify size={16} /></Tool>
      <Divider />
      <Tool label="editorBullets" active={editor.isActive("bulletList")} disabled={disabled} onClick={() => c().toggleBulletList().run()}><List size={16} /></Tool>
      <Tool label="editorNumbers" active={editor.isActive("orderedList")} disabled={disabled} onClick={() => c().toggleOrderedList().run()}><ListOrdered size={16} /></Tool>
    </div>
  );
}

export function PetitionEditor({ doc, disabled = false, onChange, onReady }: {
  doc: EditorDoc;
  disabled?: boolean;
  onChange: (doc: EditorDoc) => void;
  onReady?: (editor: Editor) => void;
}) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: EXTENSIONS,
    content: doc as JSONContent,
    editorProps: { attributes: { class: "petition-sheet", spellcheck: "true", lang: "tr" } },
    onUpdate: ({ editor: e }) => onChange(e.getJSON() as EditorDoc),
  });

  useEffect(() => { if (editor) onReady?.(editor); }, [editor, onReady]);
  // Without emitting an update: making it editable is not an edit.
  useEffect(() => { editor?.setEditable(!disabled, false); }, [editor, disabled]);

  if (!editor) return null;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Toolbar editor={editor} disabled={disabled} />
      <div className="min-h-0 flex-1 overflow-y-auto bg-desk px-2 py-3 sm:px-4 sm:py-6">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
