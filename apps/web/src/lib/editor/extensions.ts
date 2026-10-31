// The editor's own pieces: a font size on text (kept in points, as Word and UDF use) and a
// citation chip that stands for a source marker ([[E3]]) and cannot be typed over.
import { Extension, Node, mergeAttributes } from "@tiptap/core";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    fontSize: {
      setFontSize: (size: string) => ReturnType;
      unsetFontSize: () => ReturnType;
    };
  }
}

export const FontSize = Extension.create({
  name: "fontSize",
  addOptions() {
    return { types: ["textStyle"] };
  },
  addGlobalAttributes() {
    return [{
      types: this.options.types,
      attributes: {
        fontSize: {
          default: null,
          parseHTML: (el: HTMLElement) => el.style.fontSize || null,
          renderHTML: (attrs: { fontSize?: string | null }) =>
            attrs.fontSize ? { style: `font-size: ${attrs.fontSize}` } : {},
        },
      },
    }];
  },
  addCommands() {
    return {
      setFontSize: (size) => ({ chain }) => chain().setMark("textStyle", { fontSize: size }).run(),
      unsetFontSize: () => ({ chain }) =>
        chain().setMark("textStyle", { fontSize: null }).removeEmptyTextStyle().run(),
    };
  },
});

export const Citation = Node.create({
  name: "citation",
  group: "inline",
  inline: true,
  atom: true,
  selectable: false,
  addAttributes() {
    return { key: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "span[data-citation]" }];
  },
  renderHTML({ node, HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, {
      "data-citation": node.attrs.key,
      class: "citation-chip",
      contenteditable: "false",
    }), String(node.attrs.key).replace(/^E/, "")];
  },
  renderText({ node }) {
    return `[[${node.attrs.key}]]`;
  },
});
