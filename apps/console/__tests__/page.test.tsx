import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import Page from "../src/app/page";

test("Page renders correctly", () => {
  render(<Page />);
  expect(screen.getByText("Incidents")).toBeDefined();
});
