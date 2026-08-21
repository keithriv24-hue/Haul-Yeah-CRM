import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, PenLine } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, EmptyState, LoadingRows, SearchBar, searchMatch } from "@/components/Bits";
import { BF, f, BLOG_STATUSES } from "@/lib/fields";
import { fmtDate } from "@/lib/format";

const blank = { title: "", status: "Idea", category: "", publishDate: "", slug: "", body: "" };

const PostForm = ({ open, onOpenChange, post }) => {
  const { createRecord, updateRecord } = useApp();
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        post
          ? {
              title: f(post, BF.title) || "",
              status: f(post, BF.status) || "Idea",
              category: f(post, BF.category) || "",
              publishDate: (f(post, BF.publishDate) || "").slice(0, 10),
              slug: f(post, BF.slug) || "",
              body: f(post, BF.body) || "",
            }
          : blank
      );
    }
  }, [open, post]);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const save = async () => {
    if (!form.title.trim()) {
      toast.error("Give the post a title first.");
      return;
    }
    setSaving(true);
    const fields = {
      [BF.title]: form.title.trim(),
      [BF.status]: form.status,
      [BF.category]: form.category,
      [BF.publishDate]: form.publishDate,
      [BF.slug]: form.slug || form.title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
      [BF.body]: form.body,
    };
    try {
      if (post) await updateRecord("blog", post.id, fields);
      else await createRecord("blog", fields);
      toast.success(post ? "Post updated." : "Post saved.");
      onOpenChange(false);
    } catch {}
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="blog-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{post ? "Edit post" : "New post"}</DialogTitle>
          <DialogDescription>Write it plain and helpful. Slug fills itself if you leave it blank.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Title *</Label>
            <Input data-testid="blog-title-input" value={form.title} onChange={set("title")} />
          </div>
          <div>
            <Label>Status</Label>
            <Select value={form.status} onValueChange={(v) => setForm((s) => ({ ...s, status: v }))}>
              <SelectTrigger data-testid="blog-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{BLOG_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Category</Label>
            <Input value={form.category} onChange={set("category")} placeholder="Moving tips" />
          </div>
          <div>
            <Label>Publish date</Label>
            <Input type="date" value={form.publishDate} onChange={set("publishDate")} />
          </div>
          <div>
            <Label>Slug</Label>
            <Input value={form.slug} onChange={set("slug")} placeholder="auto-from-title" />
          </div>
          <div className="col-span-2">
            <Label>Body</Label>
            <Textarea data-testid="blog-body-input" value={form.body} onChange={set("body")} rows={8} />
          </div>
        </div>
        <Button data-testid="blog-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
          <PenLine className="w-4 h-4" /> {saving ? "Saving…" : "Save post"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

const ReadPostDialog = ({ post, onClose }) => (
  <Dialog open={!!post} onOpenChange={(v) => !v && onClose()}>
    <DialogContent data-testid="post-read-modal" className="max-w-lg max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="font-display">{post ? f(post, BF.title) : ""}</DialogTitle>
        <DialogDescription>
          {post && f(post, BF.category) && <span>{f(post, BF.category)} · </span>}
          {post && (f(post, BF.publishDate) ? fmtDate(f(post, BF.publishDate)) : "Published")}
        </DialogDescription>
      </DialogHeader>
      <p className="text-sm text-ink-2 whitespace-pre-wrap leading-relaxed">{post ? f(post, BF.body) || "No body written yet." : ""}</p>
    </DialogContent>
  </Dialog>
);

export default function Blog() {
  const { role } = useAuth();
  const isOwner = (role || "owner") === "owner";
  const { loadTable, records, tableState } = useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [reading, setReading] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    loadTable("blog");
  }, [loadTable]);

  const posts = records("blog").filter((p) => searchMatch(query, f(p, BF.title), f(p, BF.category), f(p, BF.slug), f(p, BF.body)));
  const published = posts.filter((p) => (f(p, BF.status) || "") === "Published");
  const { loading, error } = tableState("blog");

  return (
    <div data-testid="blog-page">
      <PageTitle
        title="Blog"
        subtitle={isOwner ? "Your content pipeline." : "Published posts from the team."}
        action={
          isOwner ? (
            <Button data-testid="new-post-btn" onClick={() => { setEditing(null); setModalOpen(true); }} className="gap-1.5 bg-accent hover:bg-accent-press">
              <Plus className="w-4 h-4" /> New post
            </Button>
          ) : null
        }
      />
      <InstructionBanner>
        {isOwner
          ? "Move posts left to right: Idea → Draft → In Review → Published. Only Published posts show up for the rest of the team."
          : "The finished, published posts land here — drafts and ideas stay with the owner. Tap a card to read it."}
      </InstructionBanner>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search posts…" testId="blog-search-input" />
      </div>

      {loading && !posts.length ? (
        <LoadingRows />
      ) : error && !posts.length ? (
        <EmptyState>{error}</EmptyState>
      ) : !isOwner ? (
        published.length === 0 ? (
          <EmptyState>{query ? "No published posts match that search." : "Nothing published yet. New posts show up here the moment the owner publishes them."}</EmptyState>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {published.map((p) => (
              <button
                key={p.id}
                data-testid="published-post-card"
                onClick={() => setReading(p)}
                className="text-left surface p-4 hover:border-accent transition-colors"
              >
                <div className="text-sm font-semibold text-primary leading-snug">{f(p, BF.title) || "Untitled"}</div>
                <div className="text-xs text-faint mt-1">
                  {f(p, BF.category) && <span>{f(p, BF.category)} · </span>}
                  {f(p, BF.publishDate) ? fmtDate(f(p, BF.publishDate)) : "Published"}
                </div>
                {f(p, BF.body) && <p className="text-xs text-faint mt-2 line-clamp-3">{f(p, BF.body)}</p>}
              </button>
            ))}
          </div>
        )
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {BLOG_STATUSES.map((status) => {
            const col = posts.filter((p) => (f(p, BF.status) || "Idea") === status);
            return (
              <div key={status} data-testid={`blog-col-${status.toLowerCase().replace(/\s+/g, "-")}`} className="rounded-lg border border-border bg-surface-sunk/60 p-3">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-display font-bold text-sm text-primary">{status}</h2>
                  <span className="text-xs font-bold text-faint">{col.length}</span>
                </div>
                <div className="space-y-2">
                  {col.map((p) => (
                    <button
                      key={p.id}
                      data-testid="blog-card"
                      onClick={() => { setEditing(p); setModalOpen(true); }}
                      className="w-full text-left surface p-3 hover:border-accent transition-colors"
                    >
                      <div className="text-sm font-semibold text-primary leading-snug">{f(p, BF.title) || "Untitled"}</div>
                      <div className="text-xs text-faint mt-1">
                        {f(p, BF.category) && <span>{f(p, BF.category)} · </span>}
                        {f(p, BF.publishDate) ? fmtDate(f(p, BF.publishDate)) : "No date"}
                      </div>
                      {f(p, BF.slug) && <div className="text-[10px] text-faint mt-0.5 truncate">/{f(p, BF.slug)}</div>}
                    </button>
                  ))}
                  {col.length === 0 && <div className="text-xs text-faint text-center py-4">Nothing here</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {isOwner && <PostForm open={modalOpen} onOpenChange={setModalOpen} post={editing} />}
      {!isOwner && <ReadPostDialog post={reading} onClose={() => setReading(null)} />}
    </div>
  );
}
