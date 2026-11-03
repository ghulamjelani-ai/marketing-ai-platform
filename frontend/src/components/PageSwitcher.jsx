import { useEffect, useState } from "react";
import { getFacebookPages, selectFacebookPage } from "../api/facebook";
import { toast } from "../utils/toast";

// "Posting to: [Page]" — lets someone who manages several Facebook Pages choose
// which one new posts, Autopilot and scheduled posts go to.
export default function PageSwitcher({ onChanged }) {
  const [pages, setPages] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;

    getFacebookPages()
      .then((data) => active && setPages(data.pages || []))
      .catch(() => active && setPages([]));

    return () => {
      active = false;
    };
  }, []);

  if (pages.length < 2) return null;

  const selected = pages.find((page) => page.selected)?.page_id || "";

  async function choose(pageId) {
    if (pageId === selected) return;

    setSaving(true);

    try {
      const result = await selectFacebookPage(pageId);
      setPages((list) => list.map((page) => ({ ...page, selected: page.page_id === pageId })));
      onChanged(result.page_name);
      toast.success("Page changed", `New posts will go to ${result.page_name}.`);
    } catch (error) {
      toast.error("Could not change the Page", error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <label className="dx-page-switch">
      <span>Posting to</span>
      <select
        value={selected}
        onChange={(event) => choose(event.target.value)}
        disabled={saving}
        aria-label="Facebook Page to post to"
      >
        {pages.map((page) => (
          <option key={page.page_id} value={page.page_id}>
            {page.page_name || page.page_id}
          </option>
        ))}
      </select>
    </label>
  );
}
