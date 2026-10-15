import { ComingSoon } from "@/components/ComingSoon";
import { messages } from "@/i18n";

export default function Page() {
  return <ComingSoon title={messages().nav.profile} />;
}
