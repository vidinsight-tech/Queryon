import { AppointmentsPanel } from "@/components/appointments/AppointmentsPanel";

export const metadata = { title: "Appointments — Queryon" };

export default function AppointmentsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Appointments</h1>
      <p className="text-sm text-gray-500 mb-6">
        Bookings collected by the chatbot. Confirm or cancel appointments and view contact details.
      </p>
      <AppointmentsPanel />
    </div>
  );
}
