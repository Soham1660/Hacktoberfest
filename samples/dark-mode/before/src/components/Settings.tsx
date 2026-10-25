import { Section, Row, Select } from "./ui";
import { useSettings } from "../hooks/useSettings";

export function Settings() {
  const { settings, update } = useSettings();

  return (
    <div className="settings">
      <Section title="Appearance">
        <Row label="Font size">
          <Select value={settings.fontSize} options={["small", "medium", "large"]} onChange={(v) => update({ fontSize: v })} />
        </Row>
      </Section>
      <Section title="Sync">
        <Row label="Sync interval">
          <Select value={settings.syncMinutes} options={[5, 15, 60]} onChange={(v) => update({ syncMinutes: v })} />
        </Row>
      </Section>
    </div>
  );
}
