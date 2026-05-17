/**
 * Server-rendered markdown for the docs site. Every element is mapped
 * to a token-only styled tag matching the `/judge` visual language
 * (DESIGN.md). No raw hex — colors come from the Tailwind tokens that
 * mirror `src/styles/tokens.css`.
 *
 * Heading ids are injected by `rehype-slug` and flow through `...rest`
 * (the `node` prop is dropped, everything else — including `id` — is
 * passed through), so the in-page TOC anchors (computed identically in
 * `lib/docs/toc.ts`) resolve correctly.
 *
 * Relative / `.md` repo links are rewritten to GitHub blob URLs so a
 * doc that cross-links a sibling file doesn't dead-end inside the app.
 */

import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";

const REPO_BLOB = "https://github.com/emark-cloud/helios/blob/main/";

function resolveHref(href: string | undefined): {
  href: string | undefined;
  external: boolean;
} {
  if (href === undefined || href.length === 0) {
    return { href, external: false };
  }
  if (href.startsWith("#")) return { href, external: false };
  if (/^https?:\/\//.test(href) || href.startsWith("mailto:")) {
    return { href, external: true };
  }
  // Repo-relative (./foo.md, ../docs/x.md, Helios.md#sec) → GitHub blob.
  const cleaned = href.replace(/^(\.\/|\/)+/, "").replace(/^(\.\.\/)+/, "");
  return { href: `${REPO_BLOB}${cleaned}`, external: true };
}

const components: Components = {
  h1({ node: _node, ...rest }) {
    return <h1 className="font-display text-2xl font-semibold text-fg-primary" {...rest} />;
  },
  h2({ node: _node, ...rest }) {
    return (
      <h2
        className="mt-10 mb-3 scroll-mt-20 border-b border-surface-line pb-2 text-[12px] font-normal uppercase tracking-[0.16em] text-fg-muted"
        {...rest}
      />
    );
  },
  h3({ node: _node, ...rest }) {
    return (
      <h3
        className="mt-7 scroll-mt-20 font-display text-base font-semibold text-fg-primary"
        {...rest}
      />
    );
  },
  h4({ node: _node, ...rest }) {
    return <h4 className="mt-5 text-sm font-semibold text-fg-secondary" {...rest} />;
  },
  h5({ node: _node, ...rest }) {
    return <h5 className="mt-4 text-sm font-semibold text-fg-muted" {...rest} />;
  },
  h6({ node: _node, ...rest }) {
    return (
      <h6
        className="mt-4 text-[12px] font-semibold uppercase tracking-[0.16em] text-fg-muted"
        {...rest}
      />
    );
  },
  p({ node: _node, ...rest }) {
    return <p className="mt-3 text-sm leading-relaxed text-fg-secondary lg:text-base" {...rest} />;
  },
  ul({ node: _node, ...rest }) {
    return (
      <ul
        className="mt-3 list-disc space-y-1 pl-5 text-sm text-fg-secondary lg:text-base"
        {...rest}
      />
    );
  },
  ol({ node: _node, ...rest }) {
    return (
      <ol
        className="mt-3 list-decimal space-y-1 pl-5 text-sm text-fg-secondary lg:text-base"
        {...rest}
      />
    );
  },
  li({ node: _node, ...rest }) {
    return <li className="leading-relaxed" {...rest} />;
  },
  strong({ node: _node, ...rest }) {
    return <strong className="font-semibold text-fg-primary" {...rest} />;
  },
  em({ node: _node, ...rest }) {
    return <em className="italic" {...rest} />;
  },
  hr({ node: _node, ...rest }) {
    return <hr className="my-8 border-surface-line" {...rest} />;
  },
  blockquote({ node: _node, ...rest }) {
    return (
      <blockquote
        className="mt-4 border-l-2 border-amber-dim pl-4 text-sm italic text-fg-muted lg:text-base"
        {...rest}
      />
    );
  },
  pre({ node: _node, ...rest }) {
    return (
      <pre
        className="mt-3 overflow-x-auto rounded-md border border-surface-line bg-surface-elev px-4 py-3 font-mono text-[12px] leading-relaxed text-fg-primary"
        {...rest}
      />
    );
  },
  table({ node: _node, ...rest }) {
    return (
      <div className="mt-4 overflow-x-auto rounded-md border border-surface-line bg-surface-panel">
        <table className="w-full text-sm" {...rest} />
      </div>
    );
  },
  thead({ node: _node, ...rest }) {
    return <thead className="border-b border-surface-line" {...rest} />;
  },
  th({ node: _node, ...rest }) {
    return (
      <th
        className="px-3 py-2.5 text-left text-[12px] font-normal uppercase tracking-[0.16em] text-fg-muted"
        {...rest}
      />
    );
  },
  td({ node: _node, ...rest }) {
    return (
      <td className="border-b border-surface-line px-3 py-2 align-top text-fg-secondary" {...rest} />
    );
  },
  tr({ node: _node, ...rest }) {
    return <tr className="last:[&>td]:border-b-0" {...rest} />;
  },
  img({ node: _node, ...rest }) {
    // Markdown images are remote/unknown-dimension repo assets;
    // next/image needs static dimensions + a loader config we don't
    // want to impose on arbitrary docs content.
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="mt-3 rounded-md border border-surface-line" alt="" {...rest} />;
  },
  code({ node: _node, className, children, ...rest }) {
    // Fenced blocks carry a `language-*` class and are wrapped by our
    // `pre` (which owns the block chrome); inline code gets the chip.
    const isBlock = typeof className === "string" && className.includes("language-");
    if (isBlock) {
      return (
        <code className={className} {...rest}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded-sm bg-surface-elev px-1 py-0.5 font-mono text-[12px] text-fg-primary"
        {...rest}
      >
        {children}
      </code>
    );
  },
  a({ node: _node, href, children }) {
    const resolved = resolveHref(typeof href === "string" ? href : undefined);
    return (
      <a
        href={resolved.href}
        className="text-amber underline-offset-2 hover:underline"
        {...(resolved.external ? { target: "_blank", rel: "noreferrer" } : {})}
      >
        {children}
      </a>
    );
  },
};

export function MarkdownRenderer({ source }: { source: string }): JSX.Element {
  return (
    <div className="min-w-0">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug]}
        components={components}
      >
        {source}
      </Markdown>
    </div>
  );
}
