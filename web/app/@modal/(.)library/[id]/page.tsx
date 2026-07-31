import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import EntryDetail from "@/components/EntryDetail";
import Modal from "@/components/Modal";

export default async function EntryModal({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const entry = await api.getEntry(id).catch((err) => {
    if (err instanceof ApiError) return null;
    throw err;
  });

  if (!entry) notFound();

  return (
    <Modal>
      <EntryDetail entry={entry} mode="modal" />
    </Modal>
  );
}
