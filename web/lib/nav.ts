/**
 * Which pages belong together.
 *
 * Kept out of the components so a page can render its sub-nav without
 * importing the whole header, and so the grouping is stated in one place
 * rather than implied by two separate lists.
 */

/** Entries and Records are the same corpus, read two ways. */
export const LIBRARY_TABS = [
  { href: "/library", label: "Entries" },
  { href: "/records", label: "Records" },
];

/** Configuration, kept out of the main bar and behind the gear. */
export const MANAGE_TABS = [
  { href: "/system", label: "System" },
  { href: "/skills", label: "Skills" },
  { href: "/usage", label: "Usage" },
];
