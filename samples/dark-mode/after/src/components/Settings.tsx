import { Section, Row, Select, Switch } from "./ui";
import { useSettings } from "../hooks/useSettings";
import { useTheme } from "../hooks/useTheme";

export function Settings() {
  const { settings, update } = useSettings();
  const { theme, toggle } = useTheme();

  return (
    <div className="settings">
      <Section title="Appearance">
        <Row label="Dark mode">
          <Switch checked={theme === "dark"} onChange={toggle} />
        </Row>
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
