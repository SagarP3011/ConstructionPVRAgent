import {
  aed,
  describeOption,
  fillTemplate,
  formatAed,
  formatDate,
  formatDelta,
  formatParameter,
  formatValue,
  workingDays,
} from "./format";

test("AED amounts keep cents only when there are any", () => {
  expect(formatAed(43529)).toBe("43,529");
  expect(formatAed(61419.6)).toBe("61,419.60");
  expect(formatAed(0)).toBe("0");
  expect(aed(-4929)).toBe("-AED 4,929");
  expect(aed(100440)).toBe("AED 100,440");
});

test("quantities, deltas and working days", () => {
  expect(formatDelta(200)).toBe("+200");
  expect(formatDelta(2.02)).toBe("+2.02");
  expect(formatDelta(0)).toBe("0");
  expect(workingDays(1)).toBe("1 working day");
  expect(workingDays(8)).toBe("8 working days");
});

test("ISO dates read as weekday, day, month and year", () => {
  expect(formatDate("2027-02-03")).toBe("Wed 3 Feb 2027");
  expect(formatDate("2027-02-26")).toBe("Fri 26 Feb 2027");
  expect(formatDate("2026-10-26T08:01:00Z")).toBe("Mon 26 Oct 2026");
  expect(formatDate("not a date")).toBe("not a date");
});

test("claim values use their unit", () => {
  expect(formatValue(43529, "AED")).toBe("AED 43,529");
  expect(formatValue(8, "wd")).toBe("8 wd");
  expect(formatValue("2027-02-12", "date")).toBe("2027-02-12 date");
  expect(formatValue(3, "")).toBe("3");
});

test("parameters and instruction templates", () => {
  expect(formatParameter(2.5, 0.1)).toBe("2.5");
  expect(formatParameter(3, 0.1)).toBe("3.0");
  expect(formatParameter(600, 100)).toBe("600");
  expect(formatParameter(1, 0.5)).toBe("1.0");
  expect(fillTemplate("Widen by {widen_by_m} m over {length_m} m.", { widen_by_m: 1, length_m: 600 }, { widen_by_m: 0.5, length_m: 100 })).toBe(
    "Widen by 1.0 m over 600 m.",
  );
  expect(fillTemplate("Keep {unknown}", {})).toBe("Keep {unknown}");
});

test("option descriptions", () => {
  expect(describeOption("OPT-NONE")).toBe("No extra crews");
  expect(describeOption("OPT-A330-A340")).toBe("Extra crews on A330, A340");
});
